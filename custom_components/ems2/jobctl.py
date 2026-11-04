"""Spotřebiče s plánem: ovládání z HA (nejdřív od, hotovo do, kolikrát, po něm spustit, naplánovat, zrušit další).

Formulář se drží v paměti integrace (coordinator.job_form) – po „Naplánovat“ se vrátí na výchozí hodnoty
(teď, do konce dne, 1×, nic). Naplánování posílá stejné API jako akce ems2.plan_appliance.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.button import ButtonEntity
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .api import EmsApiError
from .entity import Ems2Entity

NOTHING = "nic"


def _end_of_day() -> datetime:
    now = dt_util.now()
    return (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)) - timedelta(minutes=15)


def form(c, job_id: str) -> dict:
    f = c.job_form.setdefault(job_id, {})
    f.setdefault("earliest", None)            # None = teď
    f.setdefault("deadline", None)            # None = do konce dne
    f.setdefault("count", 1)
    f.setdefault("then", None)
    return f


def _reset(c, job_id: str) -> None:
    c.job_form[job_id] = {}
    form(c, job_id)
    c.async_update_listeners()


class _JobCtl(Ems2Entity):
    def __init__(self, c, job_id, name, key, label, icon):
        super().__init__(c, f"spotrebic_{job_id}_{key}", label, icon, group=(job_id, name))
        self._job = job_id

    @property
    def job(self) -> dict:
        jobs = (((self.d.get("advice") or {}).get("now") or {}).get("jobs")) or []
        return next((j for j in jobs if j.get("id") == self._job), {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.job)

    @property
    def f(self) -> dict:
        return form(self.coordinator, self._job)


class JobEarliest(_JobCtl, DateTimeEntity):
    _platform_domain = "datetime"

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "od", "Nejdřív od", "mdi:clock-start")

    @property
    def native_value(self):
        return self.f["earliest"] or dt_util.now().replace(second=0, microsecond=0)

    async def async_set_value(self, value: datetime) -> None:
        self.f["earliest"] = value
        self.async_write_ha_state()


class JobDeadline(_JobCtl, DateTimeEntity):
    _platform_domain = "datetime"

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "do", "Hotovo do", "mdi:flag-checkered")

    @property
    def native_value(self):
        return self.f["deadline"] or _end_of_day()

    async def async_set_value(self, value: datetime) -> None:
        self.f["deadline"] = value
        self.async_write_ha_state()


class JobCount(_JobCtl, NumberEntity):
    _platform_domain = "number"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 8
    _attr_native_step = 1

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "kolikrat", "Kolikrát", "mdi:counter")

    @property
    def native_value(self):
        return self.f["count"]

    async def async_set_native_value(self, value: float) -> None:
        self.f["count"] = int(value)
        self.async_write_ha_state()


class JobThen(_JobCtl, SelectEntity):
    _platform_domain = "select"

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "potom", "Po něm spustit", "mdi:arrow-right-bold")

    @property
    def options(self) -> list[str]:
        jobs = (((self.d.get("advice") or {}).get("now") or {}).get("jobs")) or []
        return [NOTHING] + [j.get("name") or j["id"] for j in jobs if j.get("id") != self._job and j.get("kind") == "program"]

    @property
    def current_option(self):
        t = self.f["then"]
        return t if t in self.options else NOTHING

    async def async_select_option(self, option: str) -> None:
        self.f["then"] = None if option == NOTHING else option
        self.async_write_ha_state()


class JobPlan(_JobCtl, ButtonEntity):
    _platform_domain = "button"

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "naplanovat", "Naplánovat", "mdi:calendar-check")

    async def async_press(self) -> None:
        f = self.f
        dl = f["deadline"] or _end_of_day()
        body = {"action": "add", "appliance": self._job, "count": f["count"], "deadline": dl.isoformat()}
        if f["earliest"]:
            body["earliest"] = f["earliest"].isoformat()
        if f["then"]:
            body["then"] = f["then"]
        try:
            await self.coordinator.api.jobs(body)
        except EmsApiError as e:
            raise HomeAssistantError(f"EMS 2.0: {e.message}: {'; '.join(e.problems)}") from e
        _reset(self.coordinator, self._job)
        await self.coordinator.async_request_refresh()


class JobCancel(_JobCtl, ButtonEntity):
    _platform_domain = "button"

    def __init__(self, c, job_id, name):
        super().__init__(c, job_id, name, "zrusit", "Zrušit další běh", "mdi:calendar-remove")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.jobs({"action": "cancel_next", "appliance": self._job})
        except EmsApiError as e:
            raise HomeAssistantError(f"EMS 2.0: {e.message}") from e
        await self.coordinator.async_request_refresh()
