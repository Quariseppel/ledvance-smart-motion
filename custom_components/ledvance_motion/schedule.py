"""Evaluate the configured local time and shutter conditions."""

from collections.abc import Callable, Mapping
from datetime import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_sunrise,
    async_track_sunset,
    async_track_time_change,
)
from homeassistant.helpers.sun import is_up
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_MODE,
    CONF_ACTIVE_UNTIL,
    CONF_COVERS,
    CONF_ONLY_AFTER_SUNSET,
    CONF_POLL_SECONDS,
    DEFAULT_FROM,
    DEFAULT_UNTIL,
    MODE_ALWAYS,
    MODE_FIXED,
    MODE_SUNSET,
    NIGHT_POLL_SECONDS,
    POLL_SECONDS,
)


def active_mode(options: Mapping[str, Any]) -> str:
    """Read the current mode or the setting stored in version 0.2."""
    legacy = MODE_SUNSET if options.get(CONF_ONLY_AFTER_SUNSET) else MODE_ALWAYS
    return options.get(CONF_ACTIVE_MODE, legacy)


def poll_interval(options: Mapping[str, Any]) -> int:
    """Keep the previous polling rate for entries without a custom interval."""
    default = NIGHT_POLL_SECONDS if active_mode(options) == MODE_SUNSET else POLL_SECONDS
    return int(options.get(CONF_POLL_SECONDS, default))


def within_window(now: time, start: time, end: time) -> bool:
    """Include start and exclude end, including windows across midnight."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end


class MotionSchedule:
    def __init__(self, hass: HomeAssistant, options: Mapping[str, Any]) -> None:
        self.hass = hass
        self.mode = active_mode(options)
        self.start = time.fromisoformat(options.get(CONF_ACTIVE_FROM, DEFAULT_FROM))
        self.end = time.fromisoformat(options.get(CONF_ACTIVE_UNTIL, DEFAULT_UNTIL))
        self.covers = tuple(options.get(CONF_COVERS, ()))

    @callback
    def is_active(self) -> bool:
        if self.mode == MODE_ALWAYS:
            return True
        if self.covers and all(
            self.hass.states.is_state(entity_id, "closed") for entity_id in self.covers
        ):
            return True
        if self.mode == MODE_SUNSET:
            return not is_up(self.hass)
        if self.mode == MODE_FIXED:
            return within_window(dt_util.now().time(), self.start, self.end)
        return False

    @callback
    def async_track_changes(self, handler: Callable) -> list[Callable[[], None]]:
        """Wake the motion coordinator promptly when one of its gates may change."""
        removers = []
        if self.mode == MODE_ALWAYS:
            return removers
        if self.covers:
            removers.append(async_track_state_change_event(self.hass, self.covers, handler))
        if self.mode == MODE_SUNSET:
            removers.extend(
                (async_track_sunrise(self.hass, handler), async_track_sunset(self.hass, handler))
            )
        elif self.mode == MODE_FIXED:
            for edge in (self.start, self.end):
                removers.append(
                    async_track_time_change(
                        self.hass, handler, hour=edge.hour, minute=edge.minute, second=edge.second
                    )
                )
        return removers
