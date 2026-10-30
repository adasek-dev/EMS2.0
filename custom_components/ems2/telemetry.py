"""Sestavení vzorku telemetrie ze stavů HA (bez závislosti na HA – dá se testovat samostatně)."""
from __future__ import annotations

from typing import Callable

GetState = Callable[[str], tuple[str | None, dict]]

_POWER = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}
_ENERGY = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}


def _value(get_state: GetState, entity: str | None, kind: str):
    if not entity:
        return None
    state, attrs = get_state(entity)
    if state in (None, "unknown", "unavailable", ""):
        return None
    if kind == "text":
        return str(state)[:60]
    try:
        v = float(state)
    except (TypeError, ValueError):
        return None
    unit = (attrs or {}).get("unit_of_measurement")
    if kind == "power":
        v *= _POWER.get(unit, 1.0)
    elif kind == "energy":
        v *= _ENERGY.get(unit, 1.0)
    return round(v, 3)


KINDS = {"soc": "pct", "pv_w": "power", "load_w": "power", "grid_w": "power", "grid_l1_w": "power",
         "grid_l2_w": "power", "grid_l3_w": "power", "battery_w": "power", "pv_today_kwh": "energy",
         "inverter_state": "text"}


def build_sample(get_state: GetState, entities: dict[str, str], ts_iso: str, *, grid_invert: bool = False,
                 battery_invert: bool = False, mode: str | None = None, ctl: str | None = None,
                 extra: dict[str, str] | None = None) -> dict:
    s: dict = {"ts": ts_iso}
    for key, kind in KINDS.items():
        v = _value(get_state, entities.get(key), kind)
        if v is not None:
            s[key] = v
    if grid_invert:
        for k in ("grid_w", "grid_l1_w", "grid_l2_w", "grid_l3_w"):
            if k in s:
                s[k] = -s[k]
    if battery_invert and "battery_w" in s:
        s["battery_w"] = -s["battery_w"]
    if "grid_w" not in s and "grid_l1_w" in s:
        s["grid_w"] = round(s.get("grid_l1_w", 0) + s.get("grid_l2_w", 0) + s.get("grid_l3_w", 0), 3)
    if "soc" in s:
        s["soc"] = max(0.0, min(100.0, s["soc"]))
    if mode:
        s["mode"] = mode
    if ctl:
        s["ctl"] = str(ctl)[:200]
    if extra:
        ex = {}
        for name, ent in list(extra.items())[:20]:
            v = _value(get_state, ent, "power")
            if v is not None:
                ex[name] = v
        if ex:
            s["extra"] = ex
    return s


def history_points(rows: list[dict], unit: str | None) -> list[dict]:
    """Hodinové statistiky HA (průměrný výkon) → [{ts: začátek hodiny UTC, kwh}].

    rows = výstup recorder.statistics_during_period pro jednu entitu; „start“ je timestamp
    (novější HA) nebo datetime (starší HA), „mean“ průměrný výkon v jednotce senzoru.
    Záporné průměry (senzor někdy ukáže export) se berou jako 0.
    """
    from datetime import datetime, timezone

    factor = _POWER.get(unit or "W", 1.0) / 1000.0          # → kW, průměr za hodinu = kWh
    out = []
    for r in rows or []:
        mean = r.get("mean")
        st = r.get("start")
        if mean is None or st is None:
            continue
        if isinstance(st, (int, float)):
            ts = datetime.fromtimestamp(st, tz=timezone.utc)
        else:
            ts = st if st.tzinfo else st.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
        try:
            kwh = max(0.0, float(mean) * factor)
        except (TypeError, ValueError):
            continue
        out.append({"ts": ts.strftime("%Y-%m-%dT%H:00:00Z"), "kwh": round(kwh, 4)})
    return out


def sensor_values(get_state: GetState, sensors: dict | None) -> dict:
    """Prémiové senzory ze serveru {klíč: {entity, kind}} → {klíč: hodnota} (výkon ve W, teplota v °C)."""
    out = {}
    for key, spec in list((sensors or {}).items())[:12]:
        ent, kind = (spec or {}).get("entity"), (spec or {}).get("kind")
        if not ent:
            continue
        if kind == "temp":
            st, _ = get_state(ent)
            try:
                v = float(st)
            except (TypeError, ValueError):
                continue
            if -60 <= v <= 80:
                out[key] = round(v, 2)
        else:
            v = _value(get_state, ent, "power")
            if v is not None:
                out[key] = max(0.0, v)
    return out
