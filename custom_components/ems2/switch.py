"""Hlavní vypínač „EMS řídí“ a přepínače nastavení (ukládají se na server)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BOOL_SETTINGS
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([ControlSwitch(c)] + [SettingSwitch(c, k, n, i) for k, (n, i) in BOOL_SETTINGS.items()])


class ControlSwitch(Ems2Entity, SwitchEntity):
    _platform_domain = "switch"

    def __init__(self, c):
        super().__init__(c, "ridi", "EMS řídí", "mdi:robot")

    @property
    def is_on(self):
        return (self.d.get("info") or {}).get("state") == "control"

    @property
    def extra_state_attributes(self):
        i = self.d.get("info") or {}
        return {"control_allowed": i.get("control_allowed"), "reason": i.get("control_reason")}

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_control(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_control(False)


class SettingSwitch(Ems2Entity, SwitchEntity):
    _platform_domain = "switch"

    def __init__(self, c, key, name, icon):
        super().__init__(c, key, name, icon)

    @property
    def available(self) -> bool:
        return super().available and self._key in (self.d.get("settings") or {})

    @property
    def is_on(self):
        return bool((self.d.get("settings") or {}).get(self._key))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.patch_setting(self._key, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.patch_setting(self._key, False)
