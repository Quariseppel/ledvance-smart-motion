"""Expose the battery percentage reported by SMART+."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .battery import BatteryCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SmartBatterySensor(entry)])


class SmartBatterySensor(CoordinatorEntity[BatteryCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "battery"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry.runtime_data.battery)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="LEDVANCE",
            name=entry.title,
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.percent

    @property
    def extra_state_attributes(self) -> dict:
        measured_at = self.coordinator.data.measured_at
        return {"last_battery_update": measured_at.isoformat()} if measured_at else {}
