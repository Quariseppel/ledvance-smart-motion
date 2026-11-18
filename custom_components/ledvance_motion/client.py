"""Read the user's LEDVANCE cloud account using the existing client."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from custom_components.hass_ledvance.api import TuyaAPI
from custom_components.hass_ledvance.const import REGIONS
from custom_components.hass_ledvance.exceptions import (
    CannotConnect,
    InvalidAuthentication,
    InvalidUserSession,
    TooManyRequests,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .const import CONF_REFRESH, CONF_REGION, CONF_SID
from .pir import motion_dp, read_motion

AUTH_ERRORS = (InvalidAuthentication, InvalidUserSession)
CONNECTION_ERRORS = (CannotConnect, OSError)
RESPONSE_ERRORS = (ValueError, TypeError, KeyError, AttributeError)
BATTERY_CODES = ("battery_percentage", "battery_percent")


@dataclass(frozen=True)
class MotionDevice:
    name: str
    dp: str


def make_client(
    data: dict[str, Any], on_tokens: Callable[[str, str], None] | None = None
) -> TuyaAPI:
    region = REGIONS[data[CONF_REGION]]
    api = TuyaAPI(
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        endpoint=region["endpoint"],
        country_code=region["country_code"],
        on_tokens_updated=on_tokens,
    )
    api.sid = data.get(CONF_SID)
    api.refresh_token = data.get(CONF_REFRESH, "")
    return api


def discover(data: dict[str, Any]) -> tuple[dict[str, MotionDevice], dict[str, str]]:
    """Find motion devices. Retain only names, IDs, PIR fields and the session."""
    api = make_client(data)
    try:
        api.login()
        devices: dict[str, MotionDevice] = {}
        for group in api.groups():
            group_id = group.get("groupId") or group.get("locationId")
            if group_id is None:
                continue
            for device in api.devices(str(group_id)):
                dp = motion_dp(device.schema or [], device.dps or {})
                if dp is not None:
                    devices[device.dev_id] = MotionDevice(device.name, dp)
        return devices, {CONF_SID: api.sid, CONF_REFRESH: api.refresh_token}
    finally:
        api.session.close()


def fetch_motion(api: TuyaAPI, device_id: str, dp: str, source: str) -> bool | None:
    """Read the current cloud state even if the battery-powered device sleeps."""
    if not api.sid:
        api.login()
    if source == "device":
        # The same single-device query the upstream client uses in devices().
        payload = api._device_info(device_id).dps
    else:
        payload = api.get_dps(device_id)
    return read_motion(payload, dp)


def verify_motion(
    data: dict[str, Any], device_id: str, dp: str
) -> tuple[str | None, dict[str, str]]:
    """Choose a working read path. Some products report PIR only in device details."""
    api = make_client(data)
    try:
        for source in ("dps", "device"):
            try:
                active = fetch_motion(api, device_id, dp, source)
            except RESPONSE_ERRORS:
                if source == "device":
                    raise
                continue
            if active is not None:
                return source, {CONF_SID: api.sid, CONF_REFRESH: api.refresh_token}
        return None, {CONF_SID: api.sid, CONF_REFRESH: api.refresh_token}
    finally:
        api.session.close()


def battery_percent(raw: object) -> int | None:
    """Accept a reported integer percentage, including numeric strings."""
    if isinstance(raw, str):
        digits = raw.strip()
        if len(digits) <= 3 and digits.isascii() and digits.isdigit():
            raw = int(digits)
    if type(raw) is int and 0 <= raw <= 100:
        return raw
    return None


def _battery_keys(schema: list) -> tuple[str, ...]:
    codes = {
        str(row["id"]): row.get("code")
        for row in schema
        if isinstance(row, Mapping) and row.get("id") is not None
    }
    numeric = tuple(dp for dp, code in codes.items() if code in BATTERY_CODES)
    if not numeric and "4" not in codes:
        # LEDVANCE's documented battery percentage field when the schema omits it.
        numeric = ("4",)
    return (*BATTERY_CODES, *numeric)


def _read_battery_percent(payload: Mapping, keys: tuple[str, ...]) -> int | None:
    if isinstance(payload.get("dps"), Mapping):
        payload = payload["dps"]
    values = {str(key): value for key, value in payload.items()}
    for key in keys:
        value = battery_percent(values.get(key))
        if value is not None:
            return value
    return None


def fetch_battery(api: TuyaAPI, device_id: str) -> int | None:
    """Read the current battery percentage using the device's own DP schema."""
    if not api.sid:
        api.login()
    device = api._device_info(device_id)
    keys = _battery_keys(device.schema or [])
    level = _read_battery_percent(device.dps or {}, keys)
    if level is not None:
        return level
    return _read_battery_percent(api.get_dps(device_id), keys)
