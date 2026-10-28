"""Spojení se serverem."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([Connected(entry.runtime_data)])


class Connected(Ems2Entity, BinarySensorEntity):
    _platform_domain = "binary_sensor"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, c):
        super().__init__(c, "spojeni", "Spojení se serverem", "mdi:cloud-check")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self):
        return bool(self.d.get("connected"))

    @property
    def extra_state_attributes(self):
        return {"last_error": self.d.get("last_error"), "buffered_samples": self.d.get("buffered")}
