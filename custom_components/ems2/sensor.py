"""Senzory: stav domu, režim teď, ceny, plán, náklady."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MODE_NAMES, PRICE_LEVELS, STATE_NAMES
from .entity import Ems2Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([
        SiteState(c), ModeNow(c), Price(c, "cena_nakup", "Cena nákupu teď", "buy"),
        Price(c, "cena_prodej", "Cena prodeje teď", "sell"), PlanSensor(c), PlanCost(c, "today"),
        PlanCost(c, "tomorrow"), Accounting(c, "cost_kc", "naklady_dnes", "Náklady dnes"),
        Accounting(c, "savings_kc", "uspora_dnes", "Úspora dnes"), BatteryTarget(c),
        HdoTariff(c), HdoNextSwitch(c),
        Advice(c), PriceLevel(c), AdviceSocTarget(c), Billing(c),
        AdviceTime(c, "okno_levne_1h", "Nejlevnější hodina", ("cheapest", 1), "mdi:clock-check"),
        AdviceTime(c, "okno_levne_2h", "Nejlevnější 2 h", ("cheapest", 2), "mdi:clock-check"),
        AdviceTime(c, "okno_levne_3h", "Nejlevnější 3 h", ("cheapest", 3), "mdi:clock-check"),
        AdviceTime(c, "dalsi_nabijeni", "Další nabíjení ze sítě", ("block", "next_grid_charge"), "mdi:battery-clock"),
        AdviceTime(c, "dalsi_prodej", "Další prodej z baterie", ("block", "next_sell"), "mdi:cash-clock"),
        AdviceEnergy(c, "fve_zbytek_dne", "FVE zbytek dne", ("today_rest", "pv_kwh"), "mdi:solar-power"),
        AdviceEnergy(c, "fve_zitra", "FVE zítra", ("tomorrow", "pv_kwh"), "mdi:solar-power"),
        AdviceEnergy(c, "spotreba_zbytek_dne", "Spotřeba zbytek dne", ("today_rest", "load_kwh"), "mdi:home-lightning-bolt"),
        AdviceEnergy(c, "spotreba_zitra", "Spotřeba zítra", ("tomorrow", "load_kwh"), "mdi:home-lightning-bolt"),
        BoilerOut(c, "bojler_cil", "Bojler: cílová teplota", "target_c", "°C", SensorDeviceClass.TEMPERATURE),
        BoilerOut(c, "bojler_vykon", "Bojler: plánovaný výkon", "power_w", "W", SensorDeviceClass.POWER),
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


class _Hdo(Ems2Entity, SensorEntity):
    """Časy HDO od distributora (ČEZ Distribuce) – posílá server v povelu (`hdo`)."""

    @property
    def hdo(self) -> dict:
        return (self.d.get("command") or {}).get("hdo") or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self.hdo)


class HdoTariff(_Hdo):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["VT", "NT"]

    def __init__(self, c):
        super().__init__(c, "hdo_tarif", "HDO tarif", "mdi:transmission-tower")

    @property
    def native_value(self):
        return self.hdo.get("tariff")

    @property
    def extra_state_attributes(self):
        h = self.hdo
        fmt = lambda w: ", ".join(f"{a}–{b}" for a, b in (w or []))    # noqa: E731
        return {"low_tariff": h.get("low"), "next_switch": h.get("next_switch"), "next_tariff": h.get("next_tariff"),
                "remaining_min": h.get("remaining_min"), "nt_today": fmt(h.get("today")), "nt_tomorrow": fmt(h.get("tomorrow")),
                "nt_today_windows": h.get("today"), "nt_tomorrow_windows": h.get("tomorrow"),
                "signal": h.get("signal"), "fetched_at": h.get("fetched_at")}


class HdoNextSwitch(_Hdo):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, c):
        super().__init__(c, "hdo_prepnuti", "HDO další přepnutí", "mdi:clock-start")

    @property
    def native_value(self):
        v = self.hdo.get("next_switch")
        return dt_util.parse_datetime(v) if v else None

    @property
    def extra_state_attributes(self):
        return {"next_tariff": self.hdo.get("next_tariff"), "remaining_min": self.hdo.get("remaining_min")}


# ── doporučení (posílá server v povelu jako `advice`) ───────────────
class _Advice(Ems2Entity, SensorEntity):
    @property
    def adv(self) -> dict:
        return self.d.get("advice") or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self.adv)


class Advice(_Advice):
    """Doporučený režim teď – pro vlastní řízení (stav = klíč režimu, atributy = podrobnosti)."""
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(MODE_NAMES)

    def __init__(self, c):
        super().__init__(c, "doporuceni", "Doporučení", "mdi:lightbulb-auto")

    @property
    def native_value(self):
        return (self.adv.get("now") or {}).get("mode")

    @property
    def extra_state_attributes(self):
        n, nx = self.adv.get("now") or {}, self.adv.get("next") or {}
        return {"mode_name": n.get("mode_name"), "reason": n.get("reason"), "battery_w": n.get("battery_w"),
                "grid_w": n.get("grid_w"), "soc_target": n.get("soc_target"), "soc_min": n.get("soc_min"),
                "soc_max": n.get("soc_max"), "until": n.get("until"), "buy": n.get("buy"), "sell": n.get("sell"),
                "effective_price": n.get("effective_price"), "pv_surplus_w": n.get("pv_surplus_w"),
                "next_mode": nx.get("mode"), "next_mode_name": nx.get("mode_name"), "next_start": nx.get("start"),
                "flags": self.adv.get("flags"), "advice_only": self.d.get("advice_only")}


class PriceLevel(_Advice):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PRICE_LEVELS

    def __init__(self, c):
        super().__init__(c, "cenova_hladina", "Cenová hladina", "mdi:scale-unbalanced")

    @property
    def native_value(self):
        return (self.adv.get("now") or {}).get("price_level")

    @property
    def extra_state_attributes(self):
        n = self.adv.get("now") or {}
        return {"price_rank": n.get("price_rank"), "buy": n.get("buy"), "sell": n.get("sell"), "spot": n.get("spot")}


class AdviceSocTarget(_Advice):
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY

    def __init__(self, c):
        super().__init__(c, "cil_soc", "Doporučený cíl SOC", "mdi:battery-arrow-up-outline")

    @property
    def native_value(self):
        return (self.adv.get("now") or {}).get("soc_target")


class AdviceTime(_Advice):
    """Začátek okna (nejlevnější souvislé hodiny, další nabíjení / prodej)."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, c, key, name, spec, icon):
        super().__init__(c, key, name, icon)
        self._spec = spec

    def _item(self) -> dict | None:
        w = self.adv.get("windows") or {}
        kind, arg = self._spec
        if kind == "cheapest":
            return next((x for x in w.get("cheapest") or [] if x.get("hours") == arg), None)
        return w.get(arg)

    @property
    def native_value(self):
        it = self._item()
        return dt_util.parse_datetime(it["start"]) if it else None

    @property
    def extra_state_attributes(self):
        it = self._item() or {}
        return {k: it.get(k) for k in ("end", "from", "to", "day", "avg_price", "minutes_to_start", "grid_charge_kwh",
                                       "sell_kwh", "soc_end") if k in it}


class AdviceEnergy(_Advice):
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_suggested_display_precision = 1

    def __init__(self, c, key, name, spec, icon):
        super().__init__(c, key, name, icon)
        self._spec = spec

    @property
    def native_value(self):
        part = (self.adv.get("forecast") or {}).get(self._spec[0]) or {}
        return part.get(self._spec[1])


class Billing(Ems2Entity, SensorEntity):
    """Odhad vyúčtování na konci zúčtovacího období: + přeplatek, − nedoplatek (Kč)."""
    _attr_native_unit_of_measurement = "CZK"
    _attr_suggested_display_precision = 0

    def __init__(self, c):
        super().__init__(c, "vyuctovani", "Vyúčtování – odhad přeplatku", "mdi:receipt-text-check")

    @property
    def available(self) -> bool:
        return super().available and bool(self.d.get("billing"))

    @property
    def native_value(self):
        return (self.d.get("billing") or {}).get("balance_end")

    @property
    def extra_state_attributes(self):
        b = self.d.get("billing") or {}
        return {k: b.get(k) for k in ("start", "end", "cost_now", "paid_now", "balance_now", "projected", "advances_total",
                                      "fixed_month", "energy_kwh", "recommended", "recommended_rest", "forecast_basis")}


class BoilerOut(_Advice):
    """Plán ohřevu bojleru pro vlastní řízení (EMS plánuje ohřev): cílová teplota a výkon teď."""

    def __init__(self, c, key, name, field, unit, dclass):
        super().__init__(c, key, name, "mdi:water-boiler")
        self._field = field
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dclass

    @property
    def available(self) -> bool:
        return super().available and bool((self.adv.get("now") or {}).get("boiler"))

    @property
    def native_value(self):
        return ((self.adv.get("now") or {}).get("boiler") or {}).get(self._field)

    @property
    def extra_state_attributes(self):
        return (self.adv.get("now") or {}).get("boiler") or {}
