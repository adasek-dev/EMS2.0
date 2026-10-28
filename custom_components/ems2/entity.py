"""Společný základ entit EMS 2.0."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import Ems2Coordinator


class Ems2Entity(CoordinatorEntity[Ems2Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Ems2Coordinator, key: str, name: str, icon: str | None = None) -> None:
        super().__init__(coordinator)
        site = coordinator.api.site_id
        self._key = key
        self._attr_unique_id = f"{site}_{key}"
        self._attr_name = name
        self.entity_id = f"{self._platform_domain}.ems2_{key}"
        if icon:
            self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, site)}, name=f"EMS 2.0 ({site})", manufacturer="EMS 2.0",
            model="klient Home Assistant", sw_version=VERSION, entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.api.url + "/web/")

    _platform_domain = "sensor"

    @property
    def d(self) -> dict:
        return self.coordinator.data or {}
