"""Entity monitoru článků baterie (t58.py): souhrn „Baterie – články“ pro kartu a zařízení za každý modul.

Do HA se zapisuje jen změna a nejvýš jednou za 30 s – 8 modulů × desítky hodnot každých pár sekund by
zbytečně plnilo historii (recorder). Celá tabulka článků je v atributech souhrnu, které se do historie neukládají.
"""
from __future__ import annotations

import time

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import CONF_T58_CELLS, DOMAIN

MIN_WRITE_S = 30.0

# klíč → (název, jednotka, device_class, přesnost, ikona)
MODULE_KEYS = {
    "delta_mv": ("Rozdíl článků", "mV", None, 0, "mdi:delta"),
    "cell_max": ("Nejvyšší článek", "V", SensorDeviceClass.VOLTAGE, 3, None),
    "cell_min": ("Nejnižší článek", "V", SensorDeviceClass.VOLTAGE, 3, None),
    "temp_max": ("Teplota nejvyšší", "°C", SensorDeviceClass.TEMPERATURE, 1, None),
    "temp_min": ("Teplota nejnižší", "°C", SensorDeviceClass.TEMPERATURE, 1, None),
    "soc": ("SOC", "%", SensorDeviceClass.BATTERY, 0, None),
    "current": ("Proud", "A", SensorDeviceClass.CURRENT, 2, None),
    "voltage": ("Napětí modulu", "V", SensorDeviceClass.VOLTAGE, 2, None),
    "energy_wh": ("Zbývající energie", "Wh", SensorDeviceClass.ENERGY_STORAGE, 0, None),
    "balancing": ("Balancuje", "článků", None, 0, "mdi:scale-balance"),
}


def _base(c) -> tuple[str, str]:
    site = c.api.site_id
    tag = getattr(c, "tag", "")
    return (f"{site}@{tag}" if tag else site), (f"{site}_{tag}" if tag else site)


class _T58Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, c, mon) -> None:
        self.c, self.mon = c, mon
        self._last_w = -1e9
        self._last_v = object()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mon.add_listener(self._changed))

    def _value(self):
        raise NotImplementedError

    @callback
    def _changed(self) -> None:
        if self.hass is None:
            return
        v = (self.available, self._value())
        now = time.monotonic()
        prev = self._last_v
        avail_changed = not isinstance(prev, tuple) or prev[0] != v[0]
        if v != prev and (avail_changed or now - self._last_w >= MIN_WRITE_S):
            self._last_v, self._last_w = v, now
            self.async_write_ha_state()


class CellsSummary(_T58Base):
    """sensor.ems2_baterie_clanky: největší rozdíl článků (mV); v atributech celá tabulka pro kartu."""
    _attr_native_unit_of_measurement = "mV"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-heart-variant"
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"modules", "error", "packs"})

    def __init__(self, c, mon) -> None:
        super().__init__(c, mon)
        base, uid = _base(c)
        tag = getattr(c, "tag", "")
        self._attr_unique_id = f"{uid}_baterie_clanky"
        self.entity_id = f"sensor.ems2_{tag}_baterie_clanky" if tag else "sensor.ems2_baterie_clanky"
        self._attr_name = "Články – největší rozdíl"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"{base}:baterie")}, name=f"EMS 2.0{' ' + tag.upper() if tag else ''} – Baterie",
                                            manufacturer="EMS 2.0", model="baterie a řízení", via_device=(DOMAIN, base),
                                            entry_type=DeviceEntryType.SERVICE)

    @property
    def available(self) -> bool:
        return bool(self.mon.modules())

    def _value(self):
        d = [m["delta_mv"] for m in self.mon.modules() if m.get("delta_mv") is not None]
        return max(d) if d else None

    @property
    def native_value(self):
        return self._value()

    @property
    def extra_state_attributes(self) -> dict:
        mods = self.mon.modules()
        keep = ("pack", "mod", "cells", "temps", "bal", "soc", "current", "voltage", "energy_wh", "delta_mv",
                "cell_max", "cell_min", "temp_max", "temp_min", "balancing")
        return {"modules": [{k: m.get(k) for k in keep} for m in mods], "connected": self.mon.connected,
                "error": self.mon.error, "packs": len({m["pack"] for m in mods}),
                "source": f"{self.mon.host}:{self.mon.port}"}


class ModuleSensor(_T58Base):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, mon, pack: int, mod: int, key: str) -> None:
        super().__init__(c, mon)
        self.pack, self.mod, self.key = pack, mod, key
        base, uid = _base(c)
        tag = getattr(c, "tag", "")
        if key.startswith("cell_") and key[5:].isdigit():
            name, unit, dc, prec, icon = (f"Článek {int(key[5:])}", "V", SensorDeviceClass.VOLTAGE, 3, None)
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        else:
            name, unit, dc, prec, icon = MODULE_KEYS[key]
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dc
        self._attr_suggested_display_precision = prec
        if icon:
            self._attr_icon = icon
        self._attr_unique_id = f"{uid}_t58_{pack}_{mod}_{key}"
        self.entity_id = f"sensor.ems2_{tag + '_' if tag else ''}baterie_{pack}_m{mod}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"{base}:t58_{pack}_{mod}")},
                                            name=f"Baterie {pack} · modul {mod}", manufacturer="Solax", model="T58",
                                            via_device=(DOMAIN, f"{base}:baterie"))

    def _m(self) -> dict | None:
        return next((m for m in self.mon.modules() if m["pack"] == self.pack and m["mod"] == self.mod), None)

    @property
    def available(self) -> bool:
        return self._m() is not None

    def _value(self):
        m = self._m()
        if m is None:
            return None
        if self.key.startswith("cell_") and self.key[5:].isdigit():
            i = int(self.key[5:]) - 1
            return m["cells"][i] if i < len(m["cells"]) else None
        if self.key == "balancing":
            return len(m.get("balancing") or [])
        return m.get(self.key)

    @property
    def native_value(self):
        return self._value()

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.key == "balancing":
            m = self._m()
            return {"cells": (m or {}).get("balancing") or []}
        return None


def track_t58(c, entry, add) -> None:
    """Souhrn hned, zařízení modulů, jak se na sběrnici objeví."""
    mon = c.t58
    if mon is None:
        return
    cells = bool({**entry.data, **entry.options}.get(CONF_T58_CELLS))
    add([CellsSummary(c, mon)])
    seen: set[tuple[int, int]] = set()

    @callback
    def _sync() -> None:
        new = [(m["pack"], m["mod"], len(m["cells"])) for m in mon.modules() if (m["pack"], m["mod"]) not in seen]
        ents = []
        for p, md, n in new:
            seen.add((p, md))
            ents += [ModuleSensor(c, mon, p, md, k) for k in MODULE_KEYS]
            if cells:
                ents += [ModuleSensor(c, mon, p, md, f"cell_{i:02d}") for i in range(1, n + 1)]
        if ents:
            add(ents)

    _sync()
    entry.async_on_unload(mon.add_listener(_sync))
