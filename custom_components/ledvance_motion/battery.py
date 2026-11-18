"""Refresh the last reported battery percentage on its own daily schedule."""

from collections.abc import Callable
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

_LOGGER = logging.getLogger(__name__)
_DAILY = timedelta(days=1)
_RETRY = timedelta(hours=1)
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
        self, hass: HomeAssistant, entry: ConfigEntry, read_battery: Callable[[], int | None]
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
        self.data = BatteryReading()

    async def async_restore(self) -> None:
        try:
            cache = await self._store.async_load()
        except (HomeAssistantError, OSError, ValueError):
            _LOGGER.warning("Unable to restore the last SMART+ battery reading")
            return
        if not isinstance(cache, dict):
            return
        self.data = BatteryReading(
            battery_percent(cache.get("percent")), _stored_datetime(cache.get("measured_at"))
        )
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
            percent = await self.hass.async_add_executor_job(self._read)
        except _READ_ERRORS as exc:
            _LOGGER.debug("SMART+ battery refresh will retry: %s", type(exc).__name__)
            interval = _RETRY
        else:
            if percent is not None:
                reading = BatteryReading(percent, dt_util.utcnow())

        self._next_update = dt_util.utcnow() + interval
        self.update_interval = interval
        try:
            await self._store.async_save(
                {
                    "percent": reading.percent,
                    "measured_at": reading.measured_at.isoformat() if reading.measured_at else None,
                    "next_update": self._next_update.isoformat(),
                }
            )
        except (HomeAssistantError, OSError):
            _LOGGER.warning("Unable to save the last SMART+ battery reading")
        return reading
