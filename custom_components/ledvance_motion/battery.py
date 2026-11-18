"""Refresh the last reported battery percentage on its own daily schedule."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import AUTH_ERRORS, CONNECTION_ERRORS, RESPONSE_ERRORS, TooManyRequests, battery_percent
from .const import DOMAIN
from .schedule import PollingPaused

_LOGGER = logging.getLogger(__name__)
_DAILY = timedelta(days=1)
_RETRY = timedelta(hours=1)
_WAIT_FOR_VALUE = timedelta(minutes=10)
_CONFIRM_ZERO = timedelta(minutes=2)
_PAUSE_RECHECK = timedelta(minutes=5)
_MIN_DELAY = timedelta(seconds=1)
_READ_ERRORS = (*AUTH_ERRORS, *CONNECTION_ERRORS, *RESPONSE_ERRORS, TooManyRequests)


@dataclass(frozen=True)
class BatteryReading:
    percent: int | None = None
    measured_at: datetime | None = None


def battery_store(hass: HomeAssistant, entry: ConfigEntry) -> Store:
    return Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.battery")


def _stored_datetime(raw: object) -> datetime | None:
    value = dt_util.parse_datetime(raw) if isinstance(raw, str) else None
    return value if value and value.tzinfo else None


class BatteryCoordinator(DataUpdateCoordinator[BatteryReading]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry,
        read_battery: Callable[[], Awaitable[int | None]],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} battery",
            config_entry=entry,
            update_interval=_MIN_DELAY,
            always_update=False,
        )
        self._read = read_battery
        self._store = battery_store(hass, entry)
        self._next_update = dt_util.utcnow()
        self._verify_zero = False
        self.data = BatteryReading()

    async def async_restore(self) -> None:
        try:
            cache = await self._store.async_load()
        except (HomeAssistantError, OSError, ValueError):
            _LOGGER.warning("Unable to restore the last SMART+ battery reading")
            return
        if not isinstance(cache, dict):
            return
        percent = battery_percent(cache.get("percent"))
        if percent == 0 and cache.get("zero_confirmed") is not True:
            # Recheck an older 0% reading that may have come from a powered-off device.
            return
        self.data = BatteryReading(percent, _stored_datetime(cache.get("measured_at")))
        self._verify_zero = cache.get("verify_zero") is True
        now = dt_util.utcnow()
        self._next_update = min(_stored_datetime(cache.get("next_update")) or now, now + _DAILY)
        self.update_interval = max(_MIN_DELAY, self._next_update - now)

    async def _async_update_data(self) -> BatteryReading:
        now = dt_util.utcnow()
        if now < self._next_update:
            self.update_interval = max(_MIN_DELAY, self._next_update - now)
            return self.data

        reading = self.data
        interval = _DAILY
        try:
            percent = await self._read()
        except PollingPaused:
            # Keep the existing due time so a pending check runs when polling resumes.
            self.update_interval = _PAUSE_RECHECK
            return reading
        except _READ_ERRORS as exc:
            _LOGGER.debug("SMART+ battery refresh will retry: %s", type(exc).__name__)
            self._verify_zero = False
            interval = _RETRY
        else:
            if percent is None:
                self._verify_zero = False
                interval = _WAIT_FOR_VALUE
            elif percent == 0 and reading.percent != 0 and not self._verify_zero:
                # Keep the last valid reading through a single 0% during startup.
                self._verify_zero = True
                interval = _CONFIRM_ZERO
            else:
                reading = BatteryReading(percent, dt_util.utcnow())
                self._verify_zero = False

        self._next_update = dt_util.utcnow() + interval
        self.update_interval = interval
        try:
            await self._store.async_save(
                {
                    "percent": reading.percent,
                    "measured_at": reading.measured_at.isoformat() if reading.measured_at else None,
                    "next_update": self._next_update.isoformat(),
                    "verify_zero": self._verify_zero,
                    "zero_confirmed": reading.percent == 0,
                }
            )
        except (HomeAssistantError, OSError):
            _LOGGER.warning("Unable to save the last SMART+ battery reading")
        return reading
