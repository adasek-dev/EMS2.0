"""Monitor článků baterie Solax T58: pasivní odposlech sběrnice RS-485 mezi střídačem a bateriemi.

Převodník RS-485 → Ethernet (např. Waveshare ETH-RS485) v režimu „transparentní TCP“ posílá všechno, co jde po
sběrnici. Střídač (master) se ptá baterií (slave 1…8, jeden slave = jeden modul) funkcí 0x03 a moduly odpovídají.
Do sběrnice se nic neposílá – jen se čte. Rozložení hodnot (registry od 0):
  1 napětí modulu /500 V · 2 SOC (dolní bajt, 250 = 100 %) · 3 proud s16 /100 A · 4–7 min/max napětí a teplota
  8–25 napětí článků s16 /1000 V · 26–33 teploty s16 /100 °C · 34 + 2 horní bity 35 = balancování (bit 0 = článek 1)
  36 zbývající energie /10 Wh
Zprávy: [adresa, 0x03, …, CRC (Modbus, LSB první), 0x0D, 0x0A]. Dělí se podle délky (žádost 10 B, odpověď
3 + počet bajtů + 4) a kontrolního součtu – ne podle 0x0D 0x0A, ty se můžou objevit i v datech.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

MAX_SLAVE = 8
N_REGS = 37
N_CELLS, N_TEMPS = 18, 8
NEED = set(range(1, N_REGS))          # registry, bez kterých se modul neukáže (0 se nepoužívá)
STALE_S = 60.0                        # bez nových dat déle → nedostupné
PAIR_S = 1.5                          # odpověď musí přijít do 1,5 s po žádosti


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _ok(fr: bytes) -> bool:
    return len(fr) >= 6 and fr[-2:] == b"\r\n" and crc16(fr[:-4]) == (fr[-4] | fr[-3] << 8)


def _s16(v: int) -> int:
    return v - 65536 if v > 32767 else v


class T58Parser:
    """Skládá zprávy ze sběrnice a drží registry modulů. feed(bajty) → množina modulů (slave), které se změnily."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.regs: dict[int, list[int]] = {}
        self.seen: dict[int, set[int]] = {}
        self.last: dict[int, float] = {}
        self._req: tuple[int, int, int, float] | None = None
        self.frames = self.bad = 0

    def feed(self, data: bytes, now: float | None = None) -> set[int]:
        now = time.monotonic() if now is None else now
        self.buf.extend(data)
        if len(self.buf) > 8192:                 # nesmysl na sběrnici – nezahltit paměť
            del self.buf[:-512]
        changed: set[int] = set()
        while len(self.buf) >= 10:
            fr = self._take()
            if fr is None:
                break
            if fr is False:
                del self.buf[0]                  # nesedí → posun o bajt a hledat dál
                self.bad += 1
                continue
            self.frames += 1
            s = self._handle(fr, now)
            if s:
                changed.add(s)
        return changed

    def _take(self):
        """Celá platná zpráva ze začátku bufferu, None = ještě nedorazila, False = tady žádná nezačíná."""
        b = self.buf
        addr, fc = b[0], b[1]
        if addr > MAX_SLAVE or fc not in (0x03, 0x05):
            return False
        head = bytes(b[:10])
        if _ok(head):                             # žádost (0x03) nebo nastavení bitu (0x05): vždy 10 bajtů
            del b[:10]
            return head
        if fc == 0x05:
            return False
        bc = b[2]                                 # odpověď: adresa, fc, počet bajtů, data, CRC, CR LF
        if bc == 0 or bc % 2 or bc > 2 * N_REGS:
            return False
        n = 3 + bc + 4
        if len(b) < n:
            return None
        fr = bytes(b[:n])
        if not _ok(fr):
            return False
        del b[:n]
        return fr

    def _handle(self, fr: bytes, now: float) -> int | None:
        addr, fc = fr[0], fr[1]
        if fc != 0x03:
            return None
        if len(fr) == 10:                        # žádost střídače: od kterého registru a kolik
            self._req = (addr, fr[2] << 8 | fr[3], fr[4] << 8 | fr[5], now)
            return None
        if self._req is None:
            return None
        raddr, start, count, t = self._req
        n = fr[2] // 2
        slave = addr or raddr
        if slave != raddr or n != count or now - t > PAIR_S or not 1 <= slave <= MAX_SLAVE:
            self._req = None                     # odpověď nepatří k žádosti → zahodit (jinak hodnoty na špatné místo)
            return None
        self._req = None
        regs = self.regs.setdefault(slave, [0] * N_REGS)
        seen = self.seen.setdefault(slave, set())
        for i in range(n):
            pos = start + i
            if pos < N_REGS:
                regs[pos] = fr[3 + 2 * i] << 8 | fr[4 + 2 * i]
                seen.add(pos)
        self.last[slave] = now
        return slave

    def module(self, slave: int, now: float | None = None) -> dict | None:
        """Hodnoty modulu, když máme všechny registry a nejsou staré."""
        now = time.monotonic() if now is None else now
        if not NEED <= self.seen.get(slave, set()) or now - self.last.get(slave, -1e9) > STALE_S:
            return None
        r = self.regs[slave]
        v = r[1] / 500
        if not 30.0 < v < 65.0:
            return None
        cells = [round(_s16(r[8 + i]) / 1000, 3) for i in range(N_CELLS)]
        cells = [c if 2.0 < c < 5.0 else None for c in cells]
        temps = [round(_s16(r[26 + i]) / 100, 1) for i in range(N_TEMPS)]
        temps = [t if -40 < t < 90 else None for t in temps]
        return {"slave": slave, "voltage": round(v, 2), "soc": round((r[2] & 0xFF) * 100 / 250),
                "current": round(_s16(r[3]) / 100, 2), "cells": cells, "temps": temps,
                "bal": r[34] | ((r[35] & 0xC000) << 2), "energy_wh": round(r[36] / 10, 1)}


NOMINAL_AH = 50.0                     # modul T58: 18 článků LFP 50 Ah (2 moduly v sérii = baterie 5,8 kWh)
CAP_MIN_DSOC = 40.0                   # měřit jen přes aspoň 40 % SOC v kuse
CAP_KEEP = 5                          # SoH = medián posledních 5 měření
CAP_I_MIN = 2.0                       # A: pod tím baterie „stojí“ (nepřeruší měření)
CAP_GAP_S = 120.0                     # výpadek dat delší → měření zahodit
CAP_TURN_S = 300.0                    # opačný směr proudu déle než 5 min → konec měření


class CapacityMeter:
    """Skutečná kapacita modulu: počítá proud × čas (Ah) během jednoho nabíjení nebo vybíjení přes aspoň 40 % SOC.
    kapacita = Ah ÷ změna SOC. Skok SOC o víc než 2 % najednou (BMS se dorovnává u 100 %) měření zahodí."""

    def __init__(self) -> None:
        self.caps: list[float] = []
        self._s: dict | None = None

    def soh(self) -> float | None:
        if not self.caps:
            return None
        c = sorted(self.caps)
        return round(c[len(c) // 2] / NOMINAL_AH * 100, 1)

    def cap_ah(self) -> float | None:
        if not self.caps:
            return None
        c = sorted(self.caps)
        return round(c[len(c) // 2], 1)

    def update(self, current: float, soc: float, now: float) -> bool:
        """True = přibylo měření."""
        s = self._s
        d = 1 if current > CAP_I_MIN else (-1 if current < -CAP_I_MIN else 0)
        if s is not None and (now - s["t"] > CAP_GAP_S or abs(soc - s["soc_last"]) > 2.0):
            s = self._s = None                               # výpadek nebo skok SOC → znovu
        if s is None:
            if d:
                self._s = {"dir": d, "soc0": soc, "soc_last": soc, "ah": 0.0, "t": now, "turn": None}
            return False
        s["ah"] += current * (now - s["t"]) / 3600.0
        s["t"], s["soc_last"] = now, soc
        if d == -s["dir"]:
            s["turn"] = s["turn"] or now
        elif d == s["dir"]:
            s["turn"] = None
        top = (s["dir"] > 0 and soc >= 97) or (s["dir"] < 0 and soc <= 5)
        if top or (s["turn"] and now - s["turn"] >= CAP_TURN_S):
            self._s = None
            return self._finish(s, soc)
        return False

    def _finish(self, s: dict, soc: float) -> bool:
        dsoc = abs(soc - s["soc0"])
        if dsoc < CAP_MIN_DSOC or abs(s["ah"]) < 1:
            return False
        cap = abs(s["ah"]) / dsoc * 100
        if not 0.4 * NOMINAL_AH <= cap <= 1.3 * NOMINAL_AH:  # nesmysl (špatné SOC, chybějící data)
            return False
        self.caps = (self.caps + [round(cap, 2)])[-CAP_KEEP:]
        return True


def summary(m: dict) -> dict:
    """Souhrny modulu pro entity a kartu."""
    c = [x for x in m["cells"] if x is not None]
    t = [x for x in m["temps"] if x is not None]
    bal = [i + 1 for i in range(N_CELLS) if m["bal"] >> i & 1]
    return {"cell_max": max(c) if c else None, "cell_min": min(c) if c else None,
            "delta_mv": round((max(c) - min(c)) * 1000, 1) if c else None,
            "temp_max": max(t) if t else None, "temp_min": min(t) if t else None, "balancing": bal}


class T58Monitor:
    """Spojení na převodník (jedno pro celé HA), čtení na pozadí, znovupřipojení. Moduly → (pack, modul)."""

    def __init__(self, host: str, port: int, per_pack: int = 2, allowed: Callable[[], bool] | None = None) -> None:
        self.host, self.port, self.per_pack = host, int(port), max(1, int(per_pack))
        self.allowed = allowed or (lambda: True)          # premium: bez něj se k převodníku nepřipojí
        self.parser = T58Parser()
        self.connected = False
        self.error: str | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Callable[[], None]] = []
        self.users = 0
        self.meters: dict[int, CapacityMeter] = {}
        self.on_caps: Callable[[], None] | None = None    # uložit naměřené kapacity (přežijí restart HA)

    def caps_state(self) -> dict:
        return {str(s): m.caps for s, m in self.meters.items() if m.caps}

    def load_caps(self, data: dict | None) -> None:
        for s, caps in (data or {}).items():
            try:
                self.meters.setdefault(int(s), CapacityMeter()).caps = [float(x) for x in caps][-CAP_KEEP:]
            except (TypeError, ValueError):
                continue

    def _measure(self, changed: set[int], now: float) -> None:
        new = False
        for s in changed:
            m = self.parser.module(s, now)
            if m:
                soc = (self.parser.regs[s][2] & 0xFF) * 100 / 250        # přesně (0,4 %), ne zaokrouhlené
                new |= self.meters.setdefault(s, CapacityMeter()).update(m["current"], soc, now)
        if new and self.on_caps:
            try:
                self.on_caps()
            except Exception:                               # noqa: BLE001
                _LOGGER.exception("EMS 2.0: monitor článků – uložení kapacit")

    def pack_mod(self, slave: int) -> tuple[int, int]:
        return (slave - 1) // self.per_pack + 1, (slave - 1) % self.per_pack + 1

    def modules(self) -> list[dict]:
        if not self.allowed():
            return []
        out = []
        now = time.monotonic()
        for s in sorted(self.parser.regs):
            m = self.parser.module(s, now)
            if m:
                p, md = self.pack_mod(s)
                mt = self.meters.get(s)
                out.append({"pack": p, "mod": md, **m, **summary(m),
                            "soh": mt.soh() if mt else None, "cap_ah": mt.cap_ah() if mt else None})
        return out

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb) if cb in self._listeners else None

    def start(self, hass) -> None:
        if self._task is None:
            self._task = hass.async_create_background_task(self._run(), "ems2_t58")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):     # noqa: BLE001
                pass
            self._task = None

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:                               # noqa: BLE001
                _LOGGER.exception("EMS 2.0: monitor článků – posluchač")

    async def _run(self) -> None:
        delay = 5
        while True:
            writer = None
            if not self.allowed():                 # dům nemá Premium (nebo se to ještě neví) – zkusit za chvíli
                self.connected, self.error = False, "monitor článků je součástí Premium"
                self._notify()
                await asyncio.sleep(20)
                continue
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 10)
                self.connected, self.error, delay = True, None, 5
                _LOGGER.info("EMS 2.0: monitor článků připojen k %s:%s", self.host, self.port)
                last_n = 0.0
                while True:
                    data = await asyncio.wait_for(reader.read(4096), STALE_S)
                    if not data:
                        raise ConnectionError("převodník ukončil spojení")
                    if not self.allowed():
                        raise ConnectionError("monitor článků je součástí Premium")
                    changed = self.parser.feed(data)
                    if changed:
                        self._measure(changed, time.monotonic())
                    if changed and time.monotonic() - last_n >= 1.0:
                        last_n = time.monotonic()
                        self._notify()
            except asyncio.CancelledError:
                if writer:
                    writer.close()
                raise
            except (OSError, asyncio.TimeoutError, ConnectionError) as e:
                self.connected = False
                self.error = "převodník neposílá data" if isinstance(e, asyncio.TimeoutError) else str(e) or type(e).__name__
                _LOGGER.warning("EMS 2.0: monitor článků %s:%s – %s, znovu za %d s", self.host, self.port, self.error, delay)
                self._notify()
            finally:
                if writer:
                    try:
                        writer.close()
                    except Exception:                       # noqa: BLE001
                        pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)


async def probe(host: str, port: int, seconds: float = 8.0) -> tuple[bool, str]:
    """Pro nastavení: připojit se a chvíli poslouchat. (ok, zpráva pro uživatele)."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), 5)
    except (OSError, asyncio.TimeoutError) as e:
        return False, f"k převodníku se nejde připojit ({e or 'vypršel čas'})"
    p = T58Parser()
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            try:
                data = await asyncio.wait_for(reader.read(4096), max(0.1, end - time.monotonic()))
            except asyncio.TimeoutError:
                break
            if not data:
                break
            p.feed(data)
    finally:
        writer.close()
    if not p.frames:
        return False, "spojení funguje, ale nepřišla žádná data ze sběrnice (režim převodníku, rychlost, zapojení?)"
    return True, f"zachyceno {len(p.regs)} modulů"
