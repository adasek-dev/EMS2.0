"""Úroveň výstrahy ČHMÚ pro ochranu před výpadkem."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import HEATING_MODES, MANUAL_MODES, OUTAGE_LEVELS
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([OutageLevel(entry.runtime_data), ManualMode(entry.runtime_data), HeatingMode(entry.runtime_data)])


class OutageLevel(Ems2Entity, SelectEntity):
    _platform_domain = "select"
    _attr_options = list(OUTAGE_LEVELS)

    def __init__(self, c):
        super().__init__(c, "ochrana_uroven", "Ochrana: od úrovně výstrahy", "mdi:alert")

    @property
    def current_option(self):
        lvl = (self.d.get("settings") or {}).get("outage_level")
        return next((k for k, v in OUTAGE_LEVELS.items() if v == lvl), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.patch_setting("outage_level", OUTAGE_LEVELS[option])


class ManualMode(Ems2Entity, SelectEntity):
    """Režim ručního řízení (platí, když je chytré řízení vypnuté)."""
    _platform_domain = "select"
    _attr_options = list(MANUAL_MODES)

    def __init__(self, c):
        super().__init__(c, "rucni_rezim", "Ruční řízení: režim", "mdi:hand-back-right")

    @property
    def current_option(self):
        m = (self.d.get("settings") or {}).get("manual_mode")
        return next((k for k, v in MANUAL_MODES.items() if v == m), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.patch_setting("manual_mode", MANUAL_MODES[option])


class HeatingMode(Ems2Entity, SelectEntity):
    """Vytápění: smí topení (elektrokotel / TČ) brát z baterie?"""
    _platform_domain = "select"
    _attr_options = list(HEATING_MODES)

    def __init__(self, c):
        super().__init__(c, "vytapeni", "Vytápění", "mdi:radiator")

    @property
    def current_option(self):
        m = (self.d.get("settings") or {}).get("heating_mode", "off")
        return next((k for k, v in HEATING_MODES.items() if v == m), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.patch_setting("heating_mode", HEATING_MODES[option])
