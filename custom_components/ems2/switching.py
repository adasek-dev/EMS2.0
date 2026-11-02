"""Spínaná zařízení (Shelly přes Home Assistant): server říká, co má být zapnuté, klient to provede.

Povel obsahuje `devices`: [{id, entity, power_entity, on}]. `on` = None → server zatím nerozhodl, nic nedělat.
Do telemetrie jde skutečný stav (dv_<id> = 1 / 0) a příkon (dw_<id>, W).
Bez závislosti na Home Assistantu (testuje se samostatně).
"""
from __future__ import annotations

from typing import Callable

GetState = Callable[[str], tuple[str | None, dict]]
RETRY_S = 60
_ON = {"on", "true", "1"}
_OFF = {"off", "false", "0"}
_POWER = {"W": 1.0, "kW": 1000.0}


def is_on(get_state: GetState, entity: str) -> bool | None:
    st, _ = get_state(entity)
    s = str(st).lower() if st is not None else None
    return True if s in _ON else False if s in _OFF else None


def power(get_state: GetState, entity: str | None) -> float | None:
    if not entity:
        return None
    st, attrs = get_state(entity)
    try:
        return round(max(0.0, float(st) * _POWER.get((attrs or {}).get("unit_of_measurement"), 1.0)), 1)
    except (TypeError, ValueError):
        return None


def telemetry(get_state: GetState, devices: list | None) -> dict:
    out = {}
    for d in (devices or [])[:20]:
        on = is_on(get_state, d.get("entity") or "")
        if on is not None:
            out[f"dv_{d['id']}"] = 1 if on else 0
        w = power(get_state, d.get("power_entity"))
        if w is not None:
            out[f"dw_{d['id']}"] = w
    return out


def calls(get_state: GetState, devices: list | None, last: dict, now: float) -> list[tuple[str, str, dict]]:
    """Volání služeb pro zařízení, jejichž stav nesedí s povelem. `last` = {entity: (chtěný stav, čas)}."""
    out = []
    for d in (devices or [])[:20]:
        ent, want = d.get("entity"), d.get("on")
        if not ent or want is None:
            continue
        cur = is_on(get_state, ent)
        if cur is None or cur == want:
            continue
        prev = last.get(ent)
        if prev and prev[0] == want and now - prev[1] < RETRY_S:
            continue                  # už jsme posílali, počkat na změnu stavu
        last[ent] = (want, now)
        out.append(("homeassistant", "turn_on" if want else "turn_off", {"entity_id": ent}))
    return out


def value_calls(get_state: GetState, items: list | None, last: dict, now: float) -> list[tuple[str, str, dict]]:
    """Hodnoty, které server chce nastavit v HA (input_number / number – třeba teplotu bojleru ze stránky Zařízení)."""
    out = []
    for it in (items or [])[:10]:
        ent, val = it.get("entity") or "", it.get("value")
        domain = ent.split(".", 1)[0]
        if domain not in ("input_number", "number") or val is None:
            continue
        st, _ = get_state(ent)
        try:
            if st is not None and abs(float(st) - float(val)) < 0.01:
                continue
        except (TypeError, ValueError):
            pass
        prev = last.get(ent)
        if prev and prev[0] == val and now - prev[1] < RETRY_S:
            continue
        last[ent] = (val, now)
        out.append((domain, "set_value", {"entity_id": ent, "value": val}))
    return out


HEAT_STALE_S = 1200          # 20 min bez povelu ze serveru → topení zpět na běžnou teplotu / odblokovat


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def heat_calls(get_state: GetState, cmd: dict | None, last: dict, now: float, offline_s: float) -> list[tuple[str, str, dict]]:
    """Plán topení → termostat (cílová teplota do climate / number / input_number) nebo blokovací spínač.

    Bezpečnost: bez spojení déle než 20 min se termostat vrátí na běžnou teplotu a blokování se zruší;
    blokovat se nikdy nesmí, když je doma pod „nejméně“."""
    hc = ((cmd or {}).get("heating") or {}).get("ctl") or {}
    ent = hc.get("entity") or ""
    if not ent or hc.get("switch") not in ("thermostat", "block"):
        return []
    domain = ent.split(".", 1)[0]
    out = (cmd or {}).get("heat_ctl")
    stale = offline_s > HEAT_STALE_S or not out
    st, attrs = get_state(ent)
    if st is None or str(st).lower() in ("unavailable", "unknown"):
        return []
    calls: list[tuple[str, str, dict]] = []
    if hc["switch"] == "thermostat":
        target = _num(hc.get("t_norm")) if stale else _num(out.get("target_c"))
        if target is None:
            return []
        if domain == "climate":
            cur = _num((attrs or {}).get("temperature"))
            call = ("climate", "set_temperature", {"entity_id": ent, "temperature": target})
        elif domain in ("number", "input_number"):
            cur = _num(st)
            call = (domain, "set_value", {"entity_id": ent, "value": target})
        else:
            return []
        if cur is not None and abs(cur - target) < 0.05:
            return []
        key = ("heat", ent)
    else:
        block = not stale and not out.get("heat_now")
        t_in_ent = (((cmd or {}).get("sensors") or {}).get("t_in") or {}).get("entity")
        t_in = _num(get_state(t_in_ent)[0]) if t_in_ent else None
        t_min = _num(hc.get("t_min"))
        if block and t_in is not None and t_min is not None and t_in < t_min - 0.1:
            block = False                      # doma je zima → blokování vždy pustit
        cur = is_on(get_state, ent)
        if cur is block or domain not in ("switch", "input_boolean"):
            return []
        target = block
        call = (domain, "turn_on" if block else "turn_off", {"entity_id": ent})
        key = ("heat", ent)
    prev = last.get(key)
    if prev and prev[0] == target and now - prev[1] < RETRY_S:
        return []
    last[key] = (target, now)
    calls.append(call)
    return calls
