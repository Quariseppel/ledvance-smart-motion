"""Expose the motion state to Home Assistant automations."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MotionCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SmartMotionSensor(entry)])


class SmartMotionSensor(CoordinatorEntity[MotionCoordinator], BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_has_entity_name = True
    _attr_translation_key = "motion"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_motion"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="LEDVANCE",
            name=entry.title,
        )

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data
