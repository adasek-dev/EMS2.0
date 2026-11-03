"""Spojení se serverem."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ADVICE_FLAGS
from .entity import Ems2Entity, track_jobs


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([Connected(c), HdoLow(c)] + [AdviceFlag(c, k, n, i) for k, (n, i) in ADVICE_FLAGS.items()])
    track_jobs(c, entry, add, lambda j: JobRunNow(c, j))


class Connected(Ems2Entity, BinarySensorEntity):
    _platform_domain = "binary_sensor"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, c):
        super().__init__(c, "spojeni", "Spojení se serverem", "mdi:cloud-check")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self):
        return bool(self.d.get("connected"))

    @property
    def extra_state_attributes(self):
        return {"last_error": self.d.get("last_error"), "buffered_samples": self.d.get("buffered")}


class HdoLow(Ems2Entity, BinarySensorEntity):
    """Zapnuto = nízký tarif (NT) podle časů HDO od distributora."""
    _platform_domain = "binary_sensor"

    def __init__(self, c):
        super().__init__(c, "hdo_nt", "HDO nízký tarif", "mdi:cash-clock")

    @property
    def available(self) -> bool:
        return super().available and bool((self.d.get("command") or {}).get("hdo"))

    @property
    def is_on(self):
        return bool(((self.d.get("command") or {}).get("hdo") or {}).get("low"))


class AdviceFlag(Ems2Entity, BinarySensorEntity):
    """Příznak z doporučení serveru (nabíjet ze sítě, levná elektřina, přebytek FVE…) – pro automatizace."""
    _platform_domain = "binary_sensor"

    def __init__(self, c, key, name, icon):
        super().__init__(c, f"dop_{key}", name, icon)
        self._flag = key

    @property
    def available(self) -> bool:
        return super().available and self._flag in ((self.d.get("advice") or {}).get("flags") or {})

    @property
    def is_on(self):
        return bool(((self.d.get("advice") or {}).get("flags") or {}).get(self._flag))


class JobRunNow(Ems2Entity, BinarySensorEntity):
    """Spotřebič s plánem: zapnuto = podle plánu EMS ho pustit teď (pro vlastní automatizace)."""
    _platform_domain = "binary_sensor"

    def __init__(self, c, job_id):
        super().__init__(c, f"spotrebic_{job_id}_pustit", f"Spotřebič {job_id}: pustit teď", "mdi:play-circle")
        self._job = job_id

    @property
    def job(self) -> dict:
        jobs = (((self.d.get("advice") or {}).get("now") or {}).get("jobs")) or []
        return next((j for j in jobs if j.get("id") == self._job), {})

    @property
    def name(self):
        return f"{self.job.get('name') or self._job}: pustit teď"

    @property
    def available(self) -> bool:
        return super().available and bool(self.job)

    @property
    def is_on(self):
        return bool(self.job.get("run_now"))

    @property
    def extra_state_attributes(self):
        j = self.job
        return {k: j.get(k) for k in ("run_until", "next_start", "next_end", "deadline", "today", "today_done", "waiting")}
