"""Set up one SMART+ motion sensor and its read-only cloud connection."""

from asyncio import Lock as AsyncLock
from dataclasses import dataclass
from datetime import timedelta
import logging
from threading import Lock
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .battery import BatteryCoordinator, battery_store
from .client import (
    AUTH_ERRORS,
    CONNECTION_ERRORS,
    RESPONSE_ERRORS,
    TooManyRequests,
    fetch_battery,
    fetch_motion,
    make_client,
)
from .const import (
    CLOUD_BACKOFF_SECONDS,
    CONF_DP,
    CONF_REFRESH,
    CONF_SID,
    CONF_SOURCE,
    DOMAIN,
)
from .schedule import MotionSchedule, PollingPaused, poll_interval

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MotionState:
    polling_active: bool
    detected: bool | None


class MotionCoordinator(DataUpdateCoordinator[MotionState]):
    """Poll one reported field and save rotated credentials in HA's event loop."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=poll_interval(entry.options)),
            always_update=False,
        )
        self.entry = entry
        self.closed = False
        self._request_lock = AsyncLock()
        self._client_lock = Lock()
        self._blocked_until = 0.0
        self._schedule = MotionSchedule(hass, entry.options)
        self._allowed: bool | None = None
        self._device_id = entry.data[CONF_DEVICE_ID]
        self._dp = entry.data[CONF_DP]
        self._source = entry.data[CONF_SOURCE]
        self.api = make_client(dict(entry.data), self._tokens_from_worker)
        self.battery = BatteryCoordinator(hass, entry, self._async_read_battery)

    def _tokens_from_worker(self, sid: str, refresh: str) -> None:
        self.hass.loop.call_soon_threadsafe(self._save_tokens, sid, refresh)

    @callback
    def _save_tokens(self, sid: str, refresh: str) -> None:
        if self.closed or (
            self.hass.config_entries.async_get_entry(self.entry.entry_id) is not self.entry
        ):
            return
        if (sid, refresh) == (
            self.entry.data.get(CONF_SID), self.entry.data.get(CONF_REFRESH)
        ):
            return
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_SID: sid, CONF_REFRESH: refresh}
        )

    def _read_cloud(self, read, *args):
        with self._client_lock:
            if self.closed:
                return None
            if monotonic() < self._blocked_until:
                raise TooManyRequests("SMART+ rate limit")
            try:
                return read(self.api, self._device_id, *args)
            except TooManyRequests:
                self._blocked_until = monotonic() + CLOUD_BACKOFF_SECONDS
                raise

    async def _async_read_cloud(self, read, *args):
        async with self._request_lock:
            # Check again after waiting in line for the shared SMART+ session.
            if self.closed or not self._schedule.is_active():
                raise PollingPaused
            return await self.hass.async_add_executor_job(self._read_cloud, read, *args)

    async def _async_read_battery(self) -> int | None:
        return await self._async_read_cloud(fetch_battery)

    async def _async_schedule_changed(self, _event) -> None:
        if self.closed:
            return
        active = self._schedule.is_active()
        if active != self._allowed:
            await self.async_request_refresh()
        if active:
            await self.battery.async_request_refresh()

    @callback
    def async_track_schedule(self) -> None:
        for unsubscribe in self._schedule.async_track_changes(self._async_schedule_changed):
            self.entry.async_on_unload(unsubscribe)

    async def _async_update_data(self) -> MotionState:
        self._allowed = self._schedule.is_active()
        if not self._allowed:
            return MotionState(polling_active=False, detected=False)

        try:
            value = await self._async_read_cloud(fetch_motion, self._dp, self._source)
        except PollingPaused:
            self._allowed = False
            return MotionState(polling_active=False, detected=False)
        except AUTH_ERRORS:
            raise ConfigEntryAuthFailed("SMART+ login required") from None
        except TooManyRequests:
            raise UpdateFailed("SMART+ rate limit", retry_after=CLOUD_BACKOFF_SECONDS) from None
        except CONNECTION_ERRORS:
            raise UpdateFailed("SMART+ cloud unreachable") from None
        except RESPONSE_ERRORS:
            raise UpdateFailed("SMART+ returned an unreadable device response") from None

        # The time window or a shutter may have changed during the cloud request.
        self._allowed = self._schedule.is_active()
        return MotionState(polling_active=self._allowed, detected=value if self._allowed else False)

    def _close(self) -> None:
        # A cancelled executor job can still be reading on a worker thread.
        with self._client_lock:
            self.api.session.close()

    async def close_client(self) -> None:
        self.closed = True
        await self.hass.async_add_executor_job(self._close)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = MotionCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.battery.async_restore()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        coordinator.async_track_schedule()
    except BaseException:
        await coordinator.close_client()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.close_client()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await battery_store(hass, entry).async_remove()
