"""Adaptér SolaX (integrace SolaX Modbus): obecný povel EMS 2.0 → Mode 1 / Mode 8.

Čistá logika bez závislosti na Home Assistantu (dá se testovat samostatně). Vstupem je
funkce get_state(entity_id) → (stav, atributy) a povel; výstupem seznam volání služeb
(domain, service, data), která integrace provede v daném pořadí.

Převzato z Node-RED „6 · EXECUTOR“ v3.35 (jen část provedení, ekonomika je teď na serveru):
    self_use   Mode 1 Disabled, Mode 8 Disabled                (Normal Mode, nesymetrický výstup)
    hold       Mode 8 „Enabled No Discharge“
    charge     Mode 1 „Enabled Grid Control“, cílový odběr ze sítě = +W
    sell       Mode 1 „Enabled Grid Control“, cílový odběr = −W (dodávka)
    pv_export  Mode 8 „Enabled Feedin Priority“
    no_export  Mode 8 „Negative Injection Price“
Pojistky: autorepeat 900 s a watchdog (≤ 60 s zbývá → znovu Trigger), přechod Mode 8 → Mode 1
bez zrušení prodeje (v3.19), ochrana „unknown“ selectu, reset zaseknutí v (R) módu po 2 min.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

Call = tuple[str, str, dict]
GetState = Callable[[str], tuple[str | None, dict]]

MODE1_AUTOREPEAT_S = 900
MODE8_AUTOREPEAT_S = 900
MODE8_DURATION_S = 20
WATCHDOG_S = 60
STUCK_AFTER_S = 120
STUCK_COOLDOWN_S = 300
TARGET_DELTA_W = 300

MODE8_SUBMODE = {"hold": "Enabled No Discharge", "pv_export": "Enabled Feedin Priority",
                 "no_export": "Negative Injection Price"}


@dataclass
class SolaxEntities:
    prefix: str = "solax"

    def __post_init__(self):
        p = self.prefix
        self.select_main = f"select.{p}_remotecontrol_power_control"
        self.select_modbus = f"select.{p}_modbus_power_control_direct"
        self.apply = f"button.{p}_remotecontrol_apply"
        self.trigger = f"button.{p}_remotecontrol_trigger"
        self.autorepeat = f"number.{p}_remotecontrol_autorepeat_duration"
        self.autorepeat_remaining = f"sensor.{p}_remotecontrol_autorepeat_remaining"
        self.grid = f"number.{p}_remotecontrol_grid_power"
        self.active = f"number.{p}_remotecontrol_active_power"
        self.select_mode8 = f"select.{p}_remotecontrol_power_control_mode"
        self.duration_mode8 = f"number.{p}_remotecontrol_duration"
        self.trigger_mode8 = f"button.{p}_powercontrolmode8_trigger"
        self.run_mode = f"sensor.{p}_run_mode"

    def required(self) -> list[str]:
        return [self.select_main, self.select_modbus, self.trigger, self.autorepeat,
                self.active, self.select_mode8, self.trigger_mode8]

    def optional(self) -> list[str]:
        """Jen ve starších verzích SolaX Modbus – když chybí, volání se vynechá."""
        return [self.apply, self.grid, self.duration_mode8]


def _sel(e: str, o: str) -> Call:
    return ("select", "select_option", {"entity_id": e, "option": o})


def _num(e: str, v: float) -> Call:
    return ("number", "set_value", {"entity_id": e, "value": float(v)})


def _press(e: str) -> Call:
    return ("button", "press", {"entity_id": e})


@dataclass
class SolaxAdapter:
    ent: SolaxEntities = field(default_factory=SolaxEntities)
    max_import_w: int = 15000
    max_export_w: int = 15000
    # vnitřní stav (jako flow.set v Node-RED)
    last_main: str | None = None
    last_modbus: str | None = None
    last_slot: str | None = None
    last_target: int | None = None
    mode8_active: bool = False
    mode8_submode: str = "Disabled"
    want_normal_since: float | None = None
    last_stuck_reset: float = -1e9
    applied_mode: str | None = None

    def _num_state(self, get_state: GetState, e: str, default: float = 0.0) -> float:
        s, _ = get_state(e)
        try:
            return float(s)
        except (TypeError, ValueError):
            return default

    def reset(self) -> None:
        self.last_main = self.last_modbus = self.last_slot = None
        self.last_target = None

    def calls_for(self, mode: str, grid_w: int | None, slot: str, get_state: GetState,
                  now: float | None = None) -> list[Call]:
        """Volání služeb pro režim. slot = začátek čtvrthodiny (kvůli novému triggeru každý slot)."""
        now = now if now is not None else time.monotonic()
        e = self.ent
        out: list[Call] = []

        main_state, _ = get_state(e.select_main)
        if main_state in ("unknown", None):
            self.reset()
            self.mode8_active = False
            self.applied_mode = "self_use"
            return self._present([_sel(e.select_main, "Disabled"), _sel(e.select_modbus, "Disabled"),
                                  _num(e.autorepeat, 0), _press(e.apply), _press(e.trigger)], get_state)

        use_mode8 = mode in MODE8_SUBMODE
        submode = MODE8_SUBMODE.get(mode, "Disabled")
        if mode in ("charge", "sell"):
            main = "Enabled Grid Control"
            target = int(-(grid_w or 0))                       # povel: grid_w + = dodávka → SolaX: + = odběr
            target = max(-self.max_export_w, min(self.max_import_w, target))
            target = int(round(target / 100.0) * 100)
            if mode == "charge":
                target = max(target, 0)
            else:
                target = min(target, 0)
        else:
            main, target = "Disabled", None
        mode1_active = main != "Disabled"
        modbus = "Enable Power Control Mode" if mode1_active else "Disabled"
        remaining = self._num_state(get_state, e.autorepeat_remaining, 0.0)

        # zaseknutí v (R) módu: chceme Normal Mode aspoň 2 minuty, autorepeat doběhl
        wants_normal = main == "Disabled" and not use_mode8
        if wants_normal:
            if self.want_normal_since is None:
                self.want_normal_since = now
        else:
            self.want_normal_since = None
        run_mode, _ = get_state(e.run_mode)
        stuck = (wants_normal and "(R)" in str(run_mode or "") and now - self.want_normal_since >= STUCK_AFTER_S
                 and remaining <= 10 and now - self.last_stuck_reset >= STUCK_COOLDOWN_S)
        if stuck:
            self.last_stuck_reset = now

        # ── Mode 8 ─────────────────────────────────────────────
        mode8_off_to_normal = False
        ha_mode8, _ = get_state(e.select_mode8)
        if not self.mode8_active and ha_mode8 not in (None, "Disabled", "unknown", "unavailable"):
            self.mode8_active, self.mode8_submode = True, str(ha_mode8)     # po restartu HA běží Mode 8 dál
        if use_mode8:
            changed = self.mode8_submode != submode or (ha_mode8 not in (None, submode))
            watchdog = self.mode8_active and not changed and remaining <= WATCHDOG_S
            if not self.mode8_active or changed or watchdog:
                out += [_sel(e.select_mode8, submode), _num(e.duration_mode8, MODE8_DURATION_S),
                        _num(e.autorepeat, MODE8_AUTOREPEAT_S), _press(e.trigger_mode8)]
            if self.last_main != "Disabled":
                # z Mode 1 do Mode 8: Mode 1 vypnout
                out += [_sel(e.select_main, "Disabled"), _sel(e.select_modbus, "Disabled"),
                        _press(e.apply), _press(e.trigger)]
                self.last_main, self.last_modbus = "Disabled", "Disabled"
            self.mode8_active, self.mode8_submode = True, submode
        elif self.mode8_active:
            if mode1_active:
                out += [_sel(e.select_mode8, "Disabled"), _press(e.trigger_mode8)]
                self.reset()                      # vynutit plné odeslání Mode 1 hned po vypnutí Mode 8
            else:
                out += [_sel(e.select_mode8, "Disabled"), _num(e.autorepeat, 0), _press(e.trigger_mode8)]
                mode8_off_to_normal = True
            self.mode8_active, self.mode8_submode = False, "Disabled"

        # ── Mode 1 ─────────────────────────────────────────────
        if not use_mode8:
            changed = self.last_main != main or self.last_modbus != modbus or mode8_off_to_normal
            slot_changed = mode1_active and self.last_slot != slot
            watchdog = mode1_active and remaining <= WATCHDOG_S
            target_changed = mode1_active and (self.last_target is None or target is None
                                               or abs(target - self.last_target) >= TARGET_DELTA_W)
            if changed or slot_changed or watchdog or stuck or target_changed:
                out += [_sel(e.select_main, main), _sel(e.select_modbus, modbus)]
                if mode1_active:
                    out += [_num(e.grid, target), _num(e.active, target), _num(e.autorepeat, MODE1_AUTOREPEAT_S)]
                else:
                    out += [_num(e.autorepeat, 0)]
                out += [_press(e.apply), _press(e.trigger)]
                self.last_slot = slot
                self.last_target = target
            self.last_main, self.last_modbus = main, modbus

        self.applied_mode = mode
        return self._present(out, get_state)

    def _present(self, calls: list[Call], get_state: GetState) -> list[Call]:
        opt = set(self.ent.optional())
        return [c for c in calls if c[2]["entity_id"] not in opt or get_state(c[2]["entity_id"])[0] is not None]


def safe_mode(cmd: dict | None, soc: float | None, now_iso: str, offline_s: float, offline_limit_s: float) -> tuple[str, int | None, str, str]:
    """Pojistky v klientovi. Vrací (režim, grid_w, slot, důvod)."""
    if cmd is None:
        return "self_use", None, now_iso[:16], "bez povelu ze serveru"
    if offline_s > offline_limit_s:
        return "self_use", None, now_iso[:16], f"server neodpovídá {int(offline_s // 60)} min"
    if cmd.get("shadow"):
        return "self_use", None, now_iso[:16], "zkušební provoz – EMS neřídí"
    chosen = None
    for c in (cmd, cmd.get("next") or {}):
        if c and c.get("slot") and c.get("valid_until") and c["slot"] <= now_iso < c["valid_until"]:
            chosen = c
            break
    if chosen is None:
        return "self_use", None, now_iso[:16], "povel vypršel"
    mode = chosen.get("mode", "self_use")
    if soc is not None:
        if mode == "charge" and chosen.get("soc_max") is not None and soc >= float(chosen["soc_max"]):
            return "self_use", None, chosen["slot"], "nabito na strop"
        if mode == "sell" and chosen.get("soc_min") is not None and soc <= float(chosen["soc_min"]) + 1:
            return "self_use", None, chosen["slot"], "baterie na minimu, prodej končí"
    return mode, chosen.get("grid_w"), chosen["slot"], chosen.get("reason", "")
