"""Koordinátor: každých 5 s pošle měření, vyzvedne povel a (v režimu řízení) ho provede.

Bezpečnost:
  • ve zkušebním provozu klient střídač vůbec neovládá (dům může dál řídit starý systém),
  • po přechodu z řízení do zkušebního provozu jednou nastaví běžný provoz (self_use) a pustí střídač,
  • bez spojení se serverem déle než 10 min nebo po vypršení povelu → self_use,
  • nabíjení nad strop / prodej pod minimum klient sám zastaví.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import EmsApi, EmsApiError, EmsAuthError
from .const import (ACCOUNTING_INTERVAL_S, BUFFER_MAX, CONF_BATTERY_INVERT, CONF_CONTROL, CONF_ENTITIES, CONF_GRID_INVERT,
                    CONF_PREFIX, CONTROL_NONE, DEFAULT_PREFIX, DOMAIN, INFO_INTERVAL_S, OFFLINE_FALLBACK_S,
                    TELEMETRY_DEFAULTS, UPDATE_INTERVAL_S)
from . import heating, switching
from .heating import HeatingControl
from .solax import SolaxAdapter, SolaxEntities, safe_mode
from .telemetry import build_sample, history_points, sensor_values

_LOGGER = logging.getLogger(__name__)


class Ems2Coordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: EmsApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
                         config_entry=entry)
        self.entry = entry
        self.api = api
        opts = {**entry.data, **entry.options}
        prefix = opts.get(CONF_PREFIX) or DEFAULT_PREFIX
        self.advice_only = opts.get(CONF_CONTROL) == CONTROL_NONE     # jen data a doporučení, nic neřídit
        self.entities = {} if self.advice_only else {k: v.format(p=prefix) for k, v in TELEMETRY_DEFAULTS.items()}
        self.entities.update({k: v for k, v in (opts.get(CONF_ENTITIES) or {}).items() if v})
        self.grid_invert = bool(opts.get(CONF_GRID_INVERT, False))
        self.battery_invert = bool(opts.get(CONF_BATTERY_INVERT, False))
        self.adapter = SolaxAdapter(SolaxEntities(prefix))
        self.buffer: deque[dict] = deque(maxlen=BUFFER_MAX)
        self.last_ok: float | None = None
        self.connected = False
        self.last_error: str | None = None
        self.command: dict | None = None
        self.info: dict = {}
        self.settings: dict = {}
        self.plan: dict = {}
        self.accounting: dict = {}
        self.billing: dict = {}
        self.applied: dict = {"mode": None, "reason": "zatím nic", "controlling": False}
        self._controlling = False
        self.heating = HeatingControl()
        self._dev_last: dict = {}
        self.boiler_ctl = HeatingControl()
        self._heat: tuple = (None, None, None, None, None, None)
        self._last_info = -1e9
        self._last_acc = -1e9
        self._history_task: str | None = None       # requested_at úlohy, která už běží / proběhla

    # ── pomocné ──────────────────────────────────────────────────
    def _get_state(self, entity_id: str) -> tuple[str | None, dict]:
        st = self.hass.states.get(entity_id)
        return (st.state, dict(st.attributes)) if st else (None, {})

    def _heat_cfg(self) -> dict:
        """Nastavení vytápění: posílá ho server s povelem (hned po změně), jinak z nastavení."""
        hc = (self.command or {}).get("heating")
        if hc:
            return hc
        s = self.settings or {}
        return {"mode": s.get("heating_mode", "off"), "state_entity": s.get("heating_state_entity"),
                "power_entity": s.get("heating_power_entity"), "nominal_w": s.get("heating_power_w") or 0}

    def _ctl_text(self) -> str | None:
        """Co klient hlásí serveru o řízení: chyba, nebo proč neřídí (když řídí bez chyb, nic)."""
        ap = self.applied or {}
        if ap.get("error"):
            return ap["error"]
        if not ap.get("controlling"):
            return ap.get("reason")
        if self.command and ap.get("mode") != self.command.get("mode"):
            return ap.get("reason")          # pojistka klienta (povel vypršel, nabito na strop…)
        return None

    def missing_solax_entities(self) -> list[str]:
        return [e for e in self.adapter.ent.required() if self.hass.states.get(e) is None]

    async def _refresh_info(self) -> None:
        self.info = await self.api.whoami()
        s = await self.api.settings()
        self.settings = s.get("settings", {})
        self.plan = await self.api.plan(48)
        self._last_info = time.monotonic()

    async def refresh_info_now(self) -> None:
        try:
            await self._refresh_info()
        except EmsApiError as e:
            raise HomeAssistantError(e.message) from e
        self.async_update_listeners()

    # ── hlavní smyčka ────────────────────────────────────────────
    async def _async_update_data(self) -> dict:
        now = dt_util.utcnow()
        sample = build_sample(self._get_state, self.entities, now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              grid_invert=self.grid_invert, battery_invert=self.battery_invert,
                              mode=self.applied.get("mode"),
                              ctl=self._ctl_text())
        hc = self._heat_cfg()
        heat_on, heat_w = heating.read(self._get_state, hc.get("state_entity"), hc.get("power_entity"))
        if hc.get("mode", "off") != "off":
            if heat_on is not None:
                sample["heating_on"] = heat_on
            if heat_w is not None:
                sample["heating_w"] = heat_w
        extra = sensor_values(self._get_state, (self.command or {}).get("sensors"))
        bc = (self.command or {}).get("boiler") or {}
        b_on = b_w = None
        if bc:
            b_on, b_w = heating.read(self._get_state, bc.get("state_entity"), bc.get("power_entity"))
            for k, v in (("boiler", b_w), ("boiler_on", None if b_on is None else (1 if b_on else 0)),
                         ("boiler_t", heating.read_temp(self._get_state, bc.get("temp_entity"))),
                         ("boiler_tmin", heating.read_temp(self._get_state, bc.get("tmin"))),
                         ("boiler_tpv", heating.read_temp(self._get_state, bc.get("tpv")))):
                if v is not None:
                    extra[k] = v
        extra.update(switching.telemetry(self._get_state, (self.command or {}).get("devices")))
        self._heat = (heat_on, heat_w, sample.get("pv_w"), sample.get("load_w"), b_on, b_w)
        if extra:
            sample["extra"] = {**sample.get("extra", {}), **extra}
        if "soc" in sample:
            self.buffer.append(sample)
        auth_failed: EmsAuthError | None = None
        try:
            while self.buffer:
                chunk = [self.buffer[i] for i in range(min(500, len(self.buffer)))]
                try:
                    await self.api.telemetry(chunk)
                except EmsApiError as e:
                    if e.status != 422:
                        raise
                    _LOGGER.warning("server odmítl měření: %s %s", e.message, e.problems)
                for _ in chunk:
                    self.buffer.popleft()
            self.command = await self.api.command()
            self.last_ok = time.monotonic()
            self.connected = True
            self.last_error = None
            if time.monotonic() - self._last_info >= INFO_INTERVAL_S or self.command.get("plan_id") != self.plan.get("plan_id"):
                await self._refresh_info()
            task = (self.command.get("tasks") or {}).get("load_history")
            if task and task.get("requested_at") != self._history_task:
                self._history_task = task.get("requested_at")
                self.hass.async_create_background_task(self._send_load_history(int(task.get("days") or 21)),
                                                       "ems2_load_history")
            if time.monotonic() - self._last_acc >= ACCOUNTING_INTERVAL_S:
                self.accounting = (await self.api.accounting_today()).get("total", {})
                try:
                    self.billing = await self.api.billing()
                except EmsApiError as e:            # starší server bez vyúčtování
                    _LOGGER.debug("EMS 2.0 vyúčtování: %s", e)
                self._last_acc = time.monotonic()
        except EmsAuthError as e:
            self.connected = False
            self.last_error = e.message
            auth_failed = e
        except EmsApiError as e:
            self.connected = False
            self.last_error = e.message
            _LOGGER.debug("EMS 2.0: %s", e)

        await self._apply(now, sample.get("soc"))
        await self._switch_devices()
        if auth_failed is not None:
            raise ConfigEntryAuthFailed(f"EMS 2.0: {auth_failed.message}")
        return self.snapshot()

    async def _switch_devices(self) -> None:
        """Zařízení přes HA (Shelly…): zapnout / vypnout podle povelu serveru (i ve zkušebním provozu)."""
        offline = (time.monotonic() - self.last_ok) if self.last_ok else 1e9
        if not self.command or offline > OFFLINE_FALLBACK_S:
            return                      # bez serveru zařízení nechat, jak jsou
        for domain, service, data in switching.calls(self._get_state, self.command.get("devices"),
                                                     self._dev_last, time.monotonic()) + \
                switching.value_calls(self._get_state, self.command.get("set_values"), self._dev_last, time.monotonic()):
            try:
                await self.hass.services.async_call(domain, service, data, blocking=True)
                _LOGGER.info("EMS 2.0: %s %s", service, data["entity_id"])
            except Exception as e:      # noqa: BLE001
                _LOGGER.warning("EMS 2.0: %s %s selhalo: %s", service, data["entity_id"], e)

    async def _apply(self, now, soc: float | None) -> None:
        if self.advice_only:
            self.applied = {"mode": None, "reason": "jen data a doporučení – integrace střídač neřídí",
                            "controlling": False}
            return
        offline = (time.monotonic() - self.last_ok) if self.last_ok else 1e9
        mode, grid_w, slot, reason = safe_mode(self.command, soc, now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                               offline, OFFLINE_FALLBACK_S)
        server_control = bool(self.command) and not self.command.get("shadow") and offline <= OFFLINE_FALLBACK_S
        if not server_control and not self._controlling:
            self.applied = {"mode": None, "reason": reason, "controlling": False}
            return
        missing = self.missing_solax_entities()
        if missing:
            self.last_error = "chybí entity SolaX: " + ", ".join(missing[:5])
            self.applied = {"mode": None, "reason": self.last_error, "controlling": False, "error": self.last_error}
            return
        if not server_control:
            mode, grid_w = "self_use", None          # konec řízení → jednou pustit střídač do běžného provozu
        label = mode
        heat_on, heat_w, pv_w, load_w, b_on, b_w = self._heat
        hc = self._heat_cfg()
        bc = (self.command or {}).get("boiler") or {}
        devices = [
            heating.Device("topí se", self.heating, hc.get("mode") if server_control else None, heat_on, heat_w,
                           float(hc.get("nominal_w") or 0)),
            heating.Device("bojler hřeje", self.boiler_ctl, bc.get("mode") if server_control else None, b_on, b_w,
                           float(bc.get("nominal_w") or 0)),
        ]
        if heating.vt_battery_first(hc, self.command, slot):
            devices = []          # „Ve VT vždy z baterie“: ve VT baterie kryje i topení a bojler
        h = heating.decide_many(mode, devices, pv_w, load_w, time.monotonic())
        if h:
            mode, label, grid_w, reason = h
        elif mode == "charge" and server_control:
            g = heating.charge_grid_target(self.command, slot, pv_w, load_w)
            if g is not None:
                grid_w = g                    # nabíjet plánovaným výkonem bez ohledu na to, kolik dům zrovna bere
        calls = self.adapter.calls_for(mode, grid_w, slot, self._get_state)
        error = None
        for domain, service, data in calls:
            try:
                await self.hass.services.async_call(domain, service, data, blocking=True)
            except Exception as e:      # jedna chyba nesmí zastavit zbytek sekvence
                _LOGGER.warning("EMS 2.0: %s.%s %s selhalo: %s", domain, service, data.get("entity_id"), e)
                error = f"{data.get('entity_id')} {data.get('option', data.get('value', ''))}: {e}"[:200]
        if calls:
            _LOGGER.info("EMS 2.0: %s (%s) – %d volání", label, reason, len(calls))
        self._controlling = server_control
        self.applied = {"mode": label, "reason": reason, "controlling": server_control, "grid_w": grid_w, "slot": slot,
                        "error": error or (self.applied.get("error") if not calls else None)}

    async def _send_load_history(self, days: int) -> None:
        """Pošle serveru hodinové průměry spotřeby domu z dlouhodobé statistiky HA."""
        entity = self.entities.get("load_w")
        body: dict[str, Any] = {"entity": entity}
        if not entity:
            body = {"entity": "", "error": "v integraci není vybraná entita spotřeby domu"}
            try:
                await self.api.load_history(body)
            except EmsApiError:
                pass
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
            start = end - timedelta(days=max(1, min(days, 60)))
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, start, end, {entity}, "hour", None, {"mean"})
            st = self.hass.states.get(entity)
            unit = st.attributes.get("unit_of_measurement") if st else None
            body["points"] = history_points(stats.get(entity, []), unit)
            if not body["points"]:
                body = {"entity": entity, "error": f"senzor {entity} nemá v HA dlouhodobé statistiky "
                                                   "(chybí state_class: measurement nebo je recorder vypnutý)"}
        except Exception as e:      # recorder chybí, chyba databáze…
            _LOGGER.warning("EMS 2.0: historie spotřeby: %s", e)
            body = {"entity": entity, "error": f"čtení statistik HA selhalo: {e}"[:250]}
        try:
            res = await self.api.load_history(body)
            _LOGGER.info("EMS 2.0: historie spotřeby odeslána: %s", res.get("status"))
        except EmsApiError as e:
            _LOGGER.warning("EMS 2.0: historii spotřeby se nepodařilo odeslat: %s", e)
            self._history_task = None              # zkusit znovu s dalším povelem

    def snapshot(self) -> dict[str, Any]:
        return {"command": self.command, "applied": self.applied, "info": self.info, "settings": self.settings,
                "plan": self.plan, "accounting": self.accounting, "connected": self.connected,
                "last_error": self.last_error, "buffered": len(self.buffer),
                "advice": (self.command or {}).get("advice"), "advice_only": self.advice_only,
                "billing": self.billing}

    # ── zápisy z entit ───────────────────────────────────────────
    async def patch_setting(self, key: str, value: Any) -> None:
        try:
            res = await self.api.patch_settings({key: value})
        except EmsApiError as e:
            raise HomeAssistantError(f"EMS 2.0: {e.message} {' '.join(e.problems)}") from e
        self.settings = res.get("settings", self.settings)
        self.async_set_updated_data(self.snapshot())

    async def set_control(self, enabled: bool) -> None:
        try:
            await self.api.set_control(enabled)
        except EmsApiError as e:
            raise HomeAssistantError(f"EMS 2.0: {e.message}") from e
        await self.refresh_info_now()
        await self.async_request_refresh()
