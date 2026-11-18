"""Connect an existing LEDVANCE SMART+ account and verify its PIR field."""

from datetime import time
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import (
    AUTH_ERRORS,
    CONNECTION_ERRORS,
    REGIONS,
    RESPONSE_ERRORS,
    MotionDevice,
    TooManyRequests,
    discover,
    verify_motion,
)
from .const import (
    ACTIVE_MODES,
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_MODE,
    CONF_ACTIVE_UNTIL,
    CONF_COVERS,
    CONF_DP,
    CONF_ONLY_AFTER_SUNSET,
    CONF_POLL_SECONDS,
    CONF_REGION,
    CONF_SOURCE,
    DEFAULT_FROM,
    DEFAULT_UNTIL,
    DOMAIN,
    MAX_POLL_SECONDS,
    MIN_POLL_SECONDS,
    MODE_COVERS,
    MODE_FIXED,
)
from .schedule import active_mode, poll_interval


def _cloud_error(exc: Exception) -> str:
    if isinstance(exc, AUTH_ERRORS):
        return "invalid_auth"
    if isinstance(exc, TooManyRequests):
        return "rate_limited"
    if isinstance(exc, CONNECTION_ERRORS):
        return "cannot_connect"
    return "cloud_response"


_EXPECTED_ERRORS = (*AUTH_ERRORS, *CONNECTION_ERRORS, TooManyRequests, *RESPONSE_ERRORS)


class MotionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "MotionOptionsFlow":
        return MotionOptionsFlow()

    def __init__(self) -> None:
        self._account: dict[str, Any] = {}
        self._devices: dict[str, MotionDevice] = {}
        self._existing = None

    async def async_step_reauth(self, entry_data):
        self._existing = self._get_reauth_entry()
        self._account = {
            CONF_EMAIL: entry_data[CONF_EMAIL],
            CONF_REGION: entry_data[CONF_REGION],
        }
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._account = dict(user_input)
            self._account[CONF_EMAIL] = self._account[CONF_EMAIL].strip()
            if not self._account[CONF_EMAIL]:
                errors[CONF_EMAIL] = "email_required"
            else:
                try:
                    devices, tokens = await self.hass.async_add_executor_job(discover, self._account)
                except _EXPECTED_ERRORS as exc:
                    errors["base"] = _cloud_error(exc)
                else:
                    self._account.update(tokens)
                    self._devices = devices
                    if self._existing is not None:
                        original = self._existing.data[CONF_DEVICE_ID]
                        if original not in devices:
                            errors["base"] = "wrong_device"
                        else:
                            return await self.async_step_device({CONF_DEVICE_ID: original})
                    elif devices:
                        return await self.async_step_device()
                    else:
                        errors["base"] = "no_motion_devices"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=self._account.get(CONF_EMAIL, "")): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_REGION, default=self._account.get(CONF_REGION, "EU")): vol.In(
                        list(REGIONS)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input=None):
        errors = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            device = self._devices.get(device_id)
            if device is None:
                errors["base"] = "wrong_device"
            else:
                await self.async_set_unique_id(device_id)
                if self._existing is None:
                    self._abort_if_unique_id_configured()
                elif self._existing.unique_id != device_id:
                    return self.async_abort(reason="reauth_device_mismatch")
                try:
                    source, tokens = await self.hass.async_add_executor_job(
                        verify_motion, self._account, device_id, device.dp
                    )
                except _EXPECTED_ERRORS as exc:
                    errors["base"] = _cloud_error(exc)
                else:
                    self._account.update(tokens)
                    if source is None:
                        errors["base"] = "no_motion_state"
                    else:
                        data = {
                            **self._account,
                            CONF_DEVICE_ID: device_id,
                            CONF_DP: device.dp,
                            CONF_SOURCE: source,
                        }
                        if self._existing is not None:
                            return self.async_update_reload_and_abort(self._existing, data_updates=data)
                        return self.async_create_entry(title=device.name, data=data)

        devices = {
            dev_id: f"{dev.name} (…{dev_id[-4:]})"
            for dev_id, dev in self._devices.items()
            if self._existing is None or self._existing.data[CONF_DEVICE_ID] == dev_id
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID, default=next(iter(devices))): vol.In(devices)}
            ),
            errors=errors,
        )


class MotionOptionsFlow(config_entries.OptionsFlowWithReload):
    """Configure when the cloud is polled."""

    async def async_step_init(self, user_input=None):
        options = self.config_entry.options
        errors = {}
        if user_input is not None:
            options = {**options, **user_input, CONF_COVERS: user_input.get(CONF_COVERS, [])}
            mode = active_mode(options)
            if mode == MODE_FIXED:
                start = time.fromisoformat(options[CONF_ACTIVE_FROM])
                end = time.fromisoformat(options[CONF_ACTIVE_UNTIL])
                if start == end:
                    errors[CONF_ACTIVE_UNTIL] = "same_time"
            if mode == MODE_COVERS and not options[CONF_COVERS]:
                errors[CONF_COVERS] = "choose_covers"
            interval = options[CONF_POLL_SECONDS]
            if not MIN_POLL_SECONDS <= interval <= MAX_POLL_SECONDS or int(interval) != interval:
                errors[CONF_POLL_SECONDS] = "invalid_interval"
            if not errors:
                options.pop(CONF_ONLY_AFTER_SUNSET, None)
                return self.async_create_entry(data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACTIVE_MODE, default=active_mode(options)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(ACTIVE_MODES),
                            translation_key="active_mode",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_ACTIVE_FROM, default=options.get(CONF_ACTIVE_FROM, DEFAULT_FROM)
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_ACTIVE_UNTIL, default=options.get(CONF_ACTIVE_UNTIL, DEFAULT_UNTIL)
                    ): selector.TimeSelector(),
                    vol.Optional(
                        CONF_COVERS, default=options.get(CONF_COVERS, [])
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            filter=[selector.EntityFilterSelectorConfig(domain="cover")],
                            multiple=True,
                        )
                    ),
                    vol.Required(
                        CONF_POLL_SECONDS, default=poll_interval(options)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_POLL_SECONDS,
                            max=MAX_POLL_SECONDS,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
            errors=errors,
        )
