"""Společný základ entit EMS 2.0."""
from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import Ems2Coordinator


# Zařízení v HA (pod hlavním „EMS 2.0“): skupina → (název, model)
GROUPS = {
    "baterie": ("Baterie", "baterie a řízení"),
    "ceny": ("Ceny a tarif", "ceny a HDO"),
    "predpoved": ("Předpověď a náklady", "předpověď a náklady"),
    "bojler": ("Bojler", "plán ohřevu"),
    "topeni": ("Topení", "plán topení"),
}
_C, _D = EntityCategory.CONFIG, EntityCategory.DIAGNOSTIC
# klíč entity → (skupina, kratší název v rámci zařízení nebo None, kategorie)
PLACE = {
    "spojeni": ("", None, _D), "telegram_notify": ("", None, _C),
    "manual_power_w": ("", None, _C), "manual_soc": ("", None, _C),
    **{k: ("baterie", None, None) for k in ("cil_soc", "plan", "dalsi_nabijeni", "dalsi_prodej", "dop_charge_from_grid",
                                             "dop_discharge_allowed", "dop_sell_from_battery", "dop_export_allowed",
                                             "allow_battery_sell", "arb_on", "vt_battery_first", "vt_charge_on",
                                             "grid_charge_vt_only", "balancing", "force_balance", "outage_protection")},
    "baterie_plan_w": ("baterie", "Plánovaný výkon", None),
    **{k: ("baterie", None, _C) for k in ("ochrana_uroven", "arb_min_profit", "vt_charge_min_gain", "grid_charge_max_soc",
                                           "balancing_interval_days", "outage_target_soc", "outage_hold_soc",
                                           "outage_lookahead_h")},
    **{k: ("ceny", None, None) for k in ("cena_nakup", "cena_prodej", "cenova_hladina", "hdo_tarif", "hdo_prepnuti", "hdo_nt",
                                          "okno_levne_1h", "okno_levne_2h", "okno_levne_3h", "dop_cheap_now",
                                          "dop_expensive_now", "dop_negative_buy", "dop_negative_sell",
                                          "dop_good_time_for_appliances")},
    **{k: ("predpoved", None, None) for k in ("fve_zbytek_dne", "fve_zitra", "spotreba_zbytek_dne", "spotreba_zitra",
                                               "plan_naklady_dnes", "plan_naklady_zitra", "naklady_dnes", "uspora_dnes",
                                               "vyuctovani", "dop_pv_surplus")},
    "bojler_cil": ("bojler", "Cílová teplota", None), "bojler_vykon": ("bojler", "Plánovaný výkon", None),
    "dop_boiler_grid_now": ("bojler", "Ohřev ze sítě teď", None), "dop_boiler_pv_ok": ("bojler", "Ohřev z FVE povolen", None),
    "topeni_cil": ("topeni", "Cílová teplota", None), "topeni_vykon": ("topeni", "Plánovaný výkon", None),
    "dop_heat_now": ("topeni", "Topit teď", None), "dop_heat_preheat": ("topeni", "Předtápět", None),
    "vytapeni": ("topeni", "Režim vytápění", None),
}


class Ems2Entity(CoordinatorEntity[Ems2Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Ems2Coordinator, key: str, name: str, icon: str | None = None,
                 group: tuple[str, str] | None = None) -> None:
        """group = (id, název) vlastního zařízení (spotřebič s plánem); jinak podle PLACE."""
        super().__init__(coordinator)
        site = coordinator.api.site_id
        tag = getattr(coordinator, "tag", "")        # druhá instance (beta): vlastní entity ems2_beta_…
        self._key = key
        self._attr_unique_id = f"{site}_{tag}_{key}" if tag else f"{site}_{key}"
        grp, short, cat = PLACE.get(key, ("", None, None))
        self._attr_name = short or name
        if cat:
            self._attr_entity_category = cat
        self.entity_id = f"{self._platform_domain}.ems2_{tag}_{key}" if tag else f"{self._platform_domain}.ems2_{key}"
        if icon:
            self._attr_icon = icon
        base = f"{site}@{tag}" if tag else site
        main = f"EMS 2.0 {tag.upper()}" if tag else "EMS 2.0"
        if group:
            gid, gname, model = f"job_{group[0]}", group[1], "spotřebič s plánem"
        elif grp:
            gid, (gname, model) = grp, GROUPS[grp]
            gname = f"{main} – {gname}"
        else:
            gid = None
        if gid:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{base}:{gid}")}, name=gname, manufacturer="EMS 2.0", model=model,
                via_device=(DOMAIN, base), entry_type=DeviceEntryType.SERVICE,
                configuration_url=coordinator.api.url + "/web/")
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, base)},
                name=f"{main} ({site})", manufacturer="EMS 2.0",
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
        new = [j for j in jobs if j.get("id") and j["id"] not in seen]
        if new:
            seen.update(j["id"] for j in new)
            ents = []
            for j in new:
                e = make(j["id"], j.get("name") or j["id"])
                ents += e if isinstance(e, list) else [e]
            add(ents)

    _sync()
    entry.async_on_unload(c.async_add_listener(_sync))
