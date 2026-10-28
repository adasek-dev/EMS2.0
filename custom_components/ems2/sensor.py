"""Senzory: stav domu, režim teď, ceny, plán, náklady."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MODE_NAMES, STATE_NAMES
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([
        SiteState(c), ModeNow(c), Price(c, "cena_nakup", "Cena nákupu teď", "buy"),
        Price(c, "cena_prodej", "Cena prodeje teď", "sell"), PlanSensor(c), PlanCost(c, "today"),
        PlanCost(c, "tomorrow"), Accounting(c, "cost_kc", "naklady_dnes", "Náklady dnes"),
        Accounting(c, "savings_kc", "uspora_dnes", "Úspora dnes"), BatteryTarget(c),
    ])


class SiteState(Ems2Entity, SensorEntity):
    def __init__(self, c):
        super().__init__(c, "stav", "Stav domu", "mdi:home-lightning-bolt")

    @property
    def native_value(self):
        st = self.d.get("info", {}).get("state")
        return STATE_NAMES.get(st, st) if st else ("bez spojení" if not self.d.get("connected") else None)

    @property
    def extra_state_attributes(self):
        i = self.d.get("info", {})
        return {"site_id": i.get("site_id"), "state": i.get("state"), "control_allowed": i.get("control_allowed"),
                "control_reason": i.get("control_reason"), "has_tariff": i.get("has_tariff"),
                "last_error": self.d.get("last_error"), "buffered_samples": self.d.get("buffered")}


class ModeNow(Ems2Entity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(MODE_NAMES.values()) + ["neřídí"]

    def __init__(self, c):
        super().__init__(c, "rezim", "Režim", "mdi:battery-sync")

    @property
    def native_value(self):
        cmd = self.d.get("command") or {}
        return MODE_NAMES.get(cmd.get("mode"), "neřídí") if cmd else "neřídí"

    @property
    def extra_state_attributes(self):
        cmd = self.d.get("command") or {}
        ap = self.d.get("applied") or {}
        return {"mode": cmd.get("mode"), "reason": cmd.get("reason"), "shadow": cmd.get("shadow"),
                "slot": cmd.get("slot"), "valid_until": cmd.get("valid_until"), "battery_w": cmd.get("battery_w"),
                "grid_w": cmd.get("grid_w"), "soc_plan": cmd.get("soc_plan"), "plan_id": cmd.get("plan_id"),
                "applied_mode": ap.get("mode"), "applied_reason": ap.get("reason"), "applied_error": ap.get("error"),
                "controlling": ap.get("controlling")}


class Price(Ems2Entity, SensorEntity):
    _attr_native_unit_of_measurement = "CZK/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, c, key, name, field):
        super().__init__(c, key, name, "mdi:cash")
        self._field = field

    @property
    def native_value(self):
        return (self.d.get("command") or {}).get(self._field)


class PlanSensor(Ems2Entity, SensorEntity):
    """Stav = SOC na konci plánu, atribut slots = plán po čtvrthodinách (pro grafy, např. apexcharts)."""
    _attr_native_unit_of_measurement = "%"
    _unrecorded_attributes = frozenset({"slots"})

    def __init__(self, c):
        super().__init__(c, "plan", "Plán – SOC na konci", "mdi:chart-timeline-variant")

    @property
    def native_value(self):
        sm = (self.d.get("plan") or {}).get("summary") or {}
        return sm.get("soc_end")

    @property
    def extra_state_attributes(self):
        p = self.d.get("plan") or {}
        slots = [{"t": s["t"], "mode": s["mode"], "soc": s["soc"], "pv": s["pv"], "load": s["load"],
                  "import": s["import"], "export": s["export"], "buy": s["buy"], "sell": s["sell"], "vt": s["vt"]}
                 for s in p.get("slots", [])]
        return {"plan_id": p.get("plan_id"), "generated_at": p.get("generated_at"),
                "last_error": p.get("last_error"), "slots": slots}


class PlanCost(Ems2Entity, SensorEntity):
    _attr_native_unit_of_measurement = "CZK"
    _attr_suggested_display_precision = 2

    def __init__(self, c, day):
        name = "Plán – náklady dnes" if day == "today" else "Plán – náklady zítra"
        super().__init__(c, f"plan_naklady_{'dnes' if day == 'today' else 'zitra'}", name, "mdi:cash-clock")
        self._day = day

    @property
    def native_value(self):
        sm = (self.d.get("plan") or {}).get("summary") or {}
        return (sm.get("cost_by_day") or {}).get(self._day)


class Accounting(Ems2Entity, SensorEntity):
    _attr_native_unit_of_measurement = "CZK"
    _attr_suggested_display_precision = 2

    def __init__(self, c, field, key, name):
        super().__init__(c, key, name, "mdi:cash-multiple")
        self._field = field

    @property
    def native_value(self):
        return (self.d.get("accounting") or {}).get(self._field)


class BatteryTarget(Ems2Entity, SensorEntity):
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(self, c):
        super().__init__(c, "baterie_plan_w", "Plánovaný výkon baterie", "mdi:battery-charging")

    @property
    def native_value(self):
        return (self.d.get("command") or {}).get("battery_w")
