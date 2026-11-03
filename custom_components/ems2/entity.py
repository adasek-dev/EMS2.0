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
        tag = getattr(coordinator, "tag", "")        # druhá instance (beta): vlastní entity ems2_beta_…
        self._key = key
        self._attr_unique_id = f"{site}_{tag}_{key}" if tag else f"{site}_{key}"
        self._attr_name = name
        self.entity_id = f"{self._platform_domain}.ems2_{tag}_{key}" if tag else f"{self._platform_domain}.ems2_{key}"
        if icon:
            self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{site}@{tag}" if tag else site)},
            name=f"EMS 2.0 {tag.upper()} ({site})" if tag else f"EMS 2.0 ({site})", manufacturer="EMS 2.0",
            model="klient Home Assistant", sw_version=VERSION, entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.api.url + "/web/")

    _platform_domain = "sensor"

    @property
    def d(self) -> dict:
        return self.coordinator.data or {}


def track_jobs(c, entry, add, make) -> None:
    """Entity pro spotřebiče s plánem: vytvoří je pro známé spotřebiče a doplní nové, jak se objeví v doporučení."""
    seen: set[str] = set()

    def _sync() -> None:
        jobs = ((((c.data or {}).get("advice") or {}).get("now") or {}).get("jobs")) or []
        new = [j["id"] for j in jobs if j.get("id") and j["id"] not in seen]
        if new:
            seen.update(new)
            add([make(j) for j in new])

    _sync()
    entry.async_on_unload(c.async_add_listener(_sync))
