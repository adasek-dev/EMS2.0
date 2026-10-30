"""Spojení se serverem."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ADVICE_FLAGS
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([Connected(c), HdoLow(c)] + [AdviceFlag(c, k, n, i) for k, (n, i) in ADVICE_FLAGS.items()])


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


class HdoLow(Ems2Entity, BinarySensorEntity):
    """Zapnuto = nízký tarif (NT) podle časů HDO od distributora."""
    _platform_domain = "binary_sensor"

    def __init__(self, c):
        super().__init__(c, "hdo_nt", "HDO nízký tarif", "mdi:cash-clock")

    @property
    def available(self) -> bool:
        return super().available and bool((self.d.get("command") or {}).get("hdo"))

    @property
    def is_on(self):
        return bool(((self.d.get("command") or {}).get("hdo") or {}).get("low"))


class AdviceFlag(Ems2Entity, BinarySensorEntity):
    """Příznak z doporučení serveru (nabíjet ze sítě, levná elektřina, přebytek FVE…) – pro automatizace."""
    _platform_domain = "binary_sensor"

    def __init__(self, c, key, name, icon):
        super().__init__(c, f"dop_{key}", name, icon)
        self._flag = key

    @property
    def available(self) -> bool:
        return super().available and self._flag in ((self.d.get("advice") or {}).get("flags") or {})

    @property
    def is_on(self):
        return bool(((self.d.get("advice") or {}).get("flags") or {}).get(self._flag))
