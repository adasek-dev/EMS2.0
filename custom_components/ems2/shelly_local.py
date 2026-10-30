"""Zařízení Shelly v síti domu: server rozhodne (zapnout / vypnout / jen měřit), integrace provede.

Gen2+ (Plus, Pro, Gen3/4): RPC  /rpc/Switch.GetStatus?id=N, /rpc/Switch.Set?id=N&on=true
Gen1 (Plug S, 1PM, 2.5):   REST /status (relays, meters), /relay/N?turn=on
Generace se zjistí z /shelly (Gen2+ vrací "gen"). Zařízení s heslem (ověřením) se nepodporuje –
pro ně použij v EMS připojení přes Shelly Cloud.
Do telemetrie jde sh_<id> = příkon (W), sho_<id> = zapnuto (1/0), she_<id> = chyba (text).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)
POLL_S = 10            # jak často číst / přepínat (s)
RESEND_S = 120         # stejný povel znovu nejdřív po 2 min (když ho někdo ručně změnil)


def parse_status(st: dict, ch: int) -> tuple[bool | None, float | None]:
    sw = st.get(f"switch:{ch}")
    if isinstance(sw, dict):
        return sw.get("output"), sw.get("apower")
    if "output" in st or "apower" in st:            # odpověď Switch.GetStatus
        return st.get("output"), st.get("apower")
    relays, meters = st.get("relays") or [], st.get("meters") or st.get("emeters") or []
    on = relays[ch].get("ison") if len(relays) > ch else None
    pw = meters[ch].get("power") if len(meters) > ch else None
    return on, pw


class ShellyLocal:
    def __init__(self, session_getter) -> None:
        self._session = session_getter
        self._gen: dict[str, int] = {}
        self._sent: dict[int, tuple[bool, float]] = {}
        self._last = -1e9
        self.values: dict[str, Any] = {}

    async def _get(self, url: str) -> Any:
        async with self._session().get(url, timeout=4) as r:
            if r.status == 401:
                raise RuntimeError("Shelly chce heslo – vypni ověření nebo použij Shelly Cloud")
            r.raise_for_status()
            return await r.json(content_type=None)

    async def _gen_of(self, host: str) -> int:
        if host not in self._gen:
            info = await self._get(f"http://{host}/shelly")
            self._gen[host] = int(info.get("gen") or 1)
        return self._gen[host]

    async def _one(self, dev: dict) -> dict[str, Any]:
        host, ch, did, want = dev["host"], int(dev.get("channel") or 0), dev["id"], dev.get("on")
        out: dict[str, Any] = {}
        try:
            gen = await self._gen_of(host)
            if gen >= 2:
                st = await self._get(f"http://{host}/rpc/Switch.GetStatus?id={ch}")
            else:
                st = await self._get(f"http://{host}/status")
            on, pw = parse_status(st, ch)
            if want is not None and on is not None and bool(on) != bool(want):
                prev = self._sent.get(did)
                if not prev or prev[0] != bool(want) or time.monotonic() - prev[1] >= RESEND_S:
                    if gen >= 2:
                        await self._get(f"http://{host}/rpc/Switch.Set?id={ch}&on={'true' if want else 'false'}")
                    else:
                        await self._get(f"http://{host}/relay/{ch}?turn={'on' if want else 'off'}")
                    self._sent[did] = (bool(want), time.monotonic())
                    _LOGGER.info("EMS 2.0: Shelly %s → %s", host, "zapnout" if want else "vypnout")
                    on = bool(want)
            if pw is not None:
                out[f"sh_{did}"] = max(0.0, float(pw))
            if on is not None:
                out[f"sho_{did}"] = 1 if on else 0
        except Exception as e:      # noqa: BLE001 – jedno zařízení nesmí zastavit ostatní
            self._gen.pop(host, None)
            out[f"she_{did}"] = f"{host}: {e}"[:120]
            _LOGGER.debug("EMS 2.0: Shelly %s: %s", host, e)
        return out

    async def sync(self, devices: list[dict] | None) -> dict[str, Any]:
        """Jednou za POLL_S přečte a případně přepne všechna místní zařízení. Vrací hodnoty do telemetrie."""
        devices = [d for d in (devices or []) if d.get("host")][:10]
        if not devices:
            self.values = {}
            return {}
        if time.monotonic() - self._last < POLL_S:
            return self.values
        self._last = time.monotonic()
        vals: dict[str, Any] = {}
        for part in await asyncio.gather(*(self._one(d) for d in devices)):
            vals.update(part)
        self.values = vals
        return vals
