"""Vytápění (elektrokotel / tepelné čerpadlo): čtení stavu z HA a úprava povelu v reálném čase.

Server plánuje po čtvrthodinách, topení ale spíná po minutách – proto o něm rozhoduje klient:
    heating_mode = no_battery   topí se → „šetřit baterii“ (Mode 8 No Discharge), celý dům ze sítě
    heating_mode = grid_heater  topí se → Grid Control s cílovým odběrem = příkon topení
                                (nejvýš to, co FVE nepokryje); zbytek domu kryje FVE a baterie
Upravuje se jen běžný provoz a „FVE do sítě“ (kdy by baterie kryla spotřebu). Nabíjení, prodej
a šetření baterie podle plánu zůstávají. Po vypnutí topení se plán vrátí až po 2 minutách,
aby střídač necvakal při krátkých pauzách kotle.
Bez závislosti na Home Assistantu (testuje se samostatně).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

GetState = Callable[[str], tuple[str | None, dict]]

HEAT_ON_W = 200            # bez entity stavu: topí, když příkon > 200 W
OFF_DELAY_S = 120
MIN_TARGET_W = 100
SHORT_ON_W = 200           # „nevybíjet“ až když FVE nestačí aspoň o 200 W …
SHORT_OFF_W = 50           # … a zruší se, když chybí méně než 50 W (bojler s SSR bere jen přebytky)
OVERRIDE_MODES = ("self_use", "pv_export")
_ON = {"on", "true", "1", "heat", "heating", "topi", "topí", "running", "zapnuto"}
_OFF = {"off", "false", "0", "idle", "standby", "netopi", "netopí", "vypnuto"}
_POWER = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}

LABELS = {"heat_hold": "šetřit baterii (topí se)", "heat_grid": "topení ze sítě"}


def read(get_state: GetState, state_entity: str | None, power_entity: str | None) -> tuple[bool | None, float | None]:
    """(topí?, změřený příkon W). None = nevíme."""
    on = None
    if state_entity:
        st, attrs = get_state(state_entity)
        if st is not None:
            if state_entity.startswith(("climate.", "water_heater.")) and attrs.get("hvac_action"):
                on = str(attrs["hvac_action"]).lower() in ("heating", "preheating")
            elif str(st).lower() in _ON:
                on = True
            elif str(st).lower() in _OFF:
                on = False
    w = None
    if power_entity:
        st, attrs = get_state(power_entity)
        try:
            w = max(0.0, float(st) * _POWER.get((attrs or {}).get("unit_of_measurement"), 1.0))
        except (TypeError, ValueError):
            w = None
    if on is None and w is not None:
        on = w > HEAT_ON_W
    return on, (round(w, 1) if w is not None else None)


@dataclass
class HeatingControl:
    active: bool = False
    last_on: float = -1e9
    short: bool = False          # FVE nestačí (dům bere víc, než FVE vyrábí) – hystereze 200 / 50 W

    def decide(self, mode: str, policy: str | None, on: bool | None, power_w: float | None, nominal_w: float,
               pv_w: float | None, load_w: float | None, now: float) -> tuple[str, str, int | None, str] | None:
        """Vrací (režim pro střídač, štítek do telemetrie, grid_w, důvod) nebo None = beze změny."""
        if on:
            self.active, self.last_on = True, now
        elif self.active and now - self.last_on >= OFF_DELAY_S:
            self.active = False
        if policy not in ("no_battery", "grid_heater") or not self.active or mode not in OVERRIDE_MODES:
            return None
        heat = power_w if power_w is not None else (nominal_w or None)
        if policy == "grid_heater" and heat is not None and pv_w is not None and load_w is not None:
            target = min(heat, max(0.0, load_w - pv_w))
            if target < MIN_TARGET_W:
                return None                        # topení pokryje FVE, baterie se nevybíjí
            target = int(round(target / 100.0) * 100)
            return ("charge", "heat_grid", -target,
                    f"topí se – ze sítě {target} W na topení, zbytek domu z FVE a baterie")
        # bez příkonu nejde odběr ze sítě nastavit → aspoň nevybíjet baterii
        return ("hold", "heat_hold", None, "topí se – baterie se nevybíjí, dům ze sítě")


def read_temp(get_state: GetState, spec) -> float | None:
    """Teplota z čísla („45“) nebo entity (sensor / input_number). None = nevíme."""
    if spec is None or spec == "":
        return None
    try:
        return float(str(spec).replace(",", "."))
    except ValueError:
        pass
    st, _ = get_state(str(spec))
    try:
        v = float(st)
    except (TypeError, ValueError):
        return None
    return round(v, 1) if -30 <= v <= 120 else None


@dataclass
class Device:
    """Topení nebo bojler: politika baterie + stav (hystereze vypnutí)."""
    name: str
    ctrl: HeatingControl
    policy: str | None = None
    on: bool | None = None
    power_w: float | None = None
    nominal_w: float = 0.0


def decide_many(mode: str, devices: list[Device], pv_w: float | None, load_w: float | None,
                now: float) -> tuple[str, str, int | None, str] | None:
    """Společné rozhodnutí pro topení i bojler. Kdo hřeje a nesmí z baterie:
    „nevybíjet“ má přednost; jinak Grid Control na součet příkonů (nejvýš co FVE nepokryje)."""
    deficit = None if pv_w is None or load_w is None else load_w - pv_w
    act = []
    for d in devices:
        if d.on:
            d.ctrl.active, d.ctrl.last_on = True, now
        elif d.ctrl.active and now - d.ctrl.last_on >= OFF_DELAY_S:
            d.ctrl.active = False
        if deficit is not None:
            d.ctrl.short = deficit > (SHORT_OFF_W if d.ctrl.short else SHORT_ON_W)
        if not (d.ctrl.active and d.policy in ("no_battery", "grid_heater")):
            continue
        # hřeje z přebytku FVE (SSR, solární dohřev): baterie se nevybíjí sama od sebe, nic neměnit
        if d.policy == "no_battery" and deficit is not None and not d.ctrl.short:
            continue
        act.append(d)
    if not act or mode not in OVERRIDE_MODES:
        return None
    who = " a ".join(d.name for d in act)
    heats = [d.power_w if d.power_w is not None else (d.nominal_w or None) for d in act]
    if any(d.policy == "no_battery" for d in act) or any(h is None for h in heats) or pv_w is None or load_w is None:
        return ("hold", "heat_hold", None, f"{who} – baterie se nevybíjí, dům ze sítě")
    target = min(sum(heats), max(0.0, load_w - pv_w))
    if target < MIN_TARGET_W:
        return None
    target = int(round(target / 100.0) * 100)
    return ("charge", "heat_grid", -target, f"{who} – ze sítě {target} W, zbytek domu z FVE a baterie")


def vt_battery_first(heating_cfg: dict, command: dict | None, slot: str) -> bool:
    """„Ve VT vždy z baterie“ a teď je VT → topení ani bojler baterii neomezují."""
    cmd = command or {}
    cur = cmd if cmd.get("slot") == slot else (cmd.get("next") or {})
    return bool((heating_cfg or {}).get("vt_battery_first", True) and cur.get("vt"))
