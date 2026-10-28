"""Číselná nastavení (ukládají se na server)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NUMBER_SETTINGS
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([SettingNumber(c, k, *v) for k, v in NUMBER_SETTINGS.items()])


class SettingNumber(Ems2Entity, NumberEntity):
    _platform_domain = "number"
    _attr_mode = NumberMode.BOX

    def __init__(self, c, key, name, mn, mx, step, unit, icon):
        super().__init__(c, key, name, icon)
        self._attr_native_min_value = mn
        self._attr_native_max_value = mx
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def available(self) -> bool:
        return super().available and self._key in (self.d.get("settings") or {})

    @property
    def native_value(self):
        return (self.d.get("settings") or {}).get(self._key)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.patch_setting(self._key, value)
