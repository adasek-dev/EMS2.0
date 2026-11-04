"""Spotřebiče s plánem: nejdřív od / hotovo do (formulář pro „Naplánovat“)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import track_jobs
from .jobctl import JobDeadline, JobEarliest


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    # i u „jen sledovat“ (beta): plánuje se na serveru toho připojení, nic fyzicky neřídí
    track_jobs(c, entry, add, lambda j, n: [JobEarliest(c, j, n), JobDeadline(c, j, n)])
