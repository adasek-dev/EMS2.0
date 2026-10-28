"""Tlačítko: přepočítat plán hned."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import EmsApiError
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([Replan(entry.runtime_data)])


class Replan(Ems2Entity, ButtonEntity):
    _platform_domain = "button"

    def __init__(self, c):
        super().__init__(c, "prepocitat", "Přepočítat plán", "mdi:refresh")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.replan()
        except EmsApiError as e:
            raise HomeAssistantError(f"EMS 2.0: {e.message}") from e
