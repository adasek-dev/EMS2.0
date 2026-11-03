"""EMS 2.0 – integrace pro Home Assistant.

Spojí dům se serverem EMS 2.0: každých 5 s posílá měření ze SolaXu, vyzvedává povel
a v režimu řízení ho provádí. Server je jediný „mozek“, integrace je jen klient s pojistkami.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EmsApi, EmsApiError
from .const import CONF_SITE_ID, CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import Ems2Coordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.SELECT,
             Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_TARIFF_SCHEMA = vol.Schema({vol.Required("tariff"): dict, vol.Optional("entry_id"): cv.string})
REPLAN_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})
PLAN_APPLIANCE_SCHEMA = vol.Schema({
    vol.Required("appliance"): cv.string, vol.Optional("count", default=1): vol.All(vol.Coerce(int), vol.Range(1, 8)),
    vol.Optional("earliest"): cv.datetime, vol.Optional("deadline"): cv.datetime, vol.Optional("then"): cv.string,
    vol.Optional("kwh"): vol.Coerce(float), vol.Optional("entry_id"): cv.string})
CANCEL_APPLIANCE_SCHEMA = vol.Schema({vol.Required("appliance"): cv.string, vol.Optional("entry_id"): cv.string})


def _iso(v):
    from homeassistant.util import dt as dt_util
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=dt_util.get_default_time_zone())).isoformat()


def _coordinators(hass: HomeAssistant, entry_id: str | None) -> list[Ems2Coordinator]:
    entries = hass.config_entries.async_entries(DOMAIN)
    out = []
    for e in entries:
        if (entry_id is None or e.entry_id == entry_id) and getattr(e, "runtime_data", None):
            out.append(e.runtime_data)
    if not out:
        raise HomeAssistantError("EMS 2.0: integrace není nastavená")
    return out


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def set_tariff(call: ServiceCall) -> None:
        for coord in _coordinators(hass, call.data.get("entry_id")):
            try:
                await coord.api.put_tariff(call.data["tariff"])
            except EmsApiError as e:
                raise HomeAssistantError(f"EMS 2.0: {e.message}: {'; '.join(e.problems)}") from e
            await coord.refresh_info_now()

    async def replan(call: ServiceCall) -> None:
        for coord in _coordinators(hass, call.data.get("entry_id")):
            try:
                await coord.api.replan()
            except EmsApiError as e:
                raise HomeAssistantError(f"EMS 2.0: {e.message}") from e

    async def plan_appliance(call: ServiceCall) -> None:
        body = {"action": "add", "appliance": call.data["appliance"], "count": call.data.get("count", 1),
                "earliest": _iso(call.data.get("earliest")), "deadline": _iso(call.data.get("deadline")),
                "then": call.data.get("then"), "kwh": call.data.get("kwh")}
        for coord in _coordinators(hass, call.data.get("entry_id")):
            if coord.watch:
                continue
            try:
                await coord.api.jobs({k: v for k, v in body.items() if v is not None})
            except EmsApiError as e:
                raise HomeAssistantError(f"EMS 2.0: {e.message}: {'; '.join(e.problems)}") from e

    async def cancel_appliance(call: ServiceCall) -> None:
        for coord in _coordinators(hass, call.data.get("entry_id")):
            if coord.watch:
                continue
            try:
                await coord.api.jobs({"action": "cancel_next", "appliance": call.data["appliance"]})
            except EmsApiError as e:
                raise HomeAssistantError(f"EMS 2.0: {e.message}") from e

    hass.services.async_register(DOMAIN, "plan_appliance", plan_appliance, schema=PLAN_APPLIANCE_SCHEMA)
    hass.services.async_register(DOMAIN, "cancel_appliance", cancel_appliance, schema=CANCEL_APPLIANCE_SCHEMA)
    hass.services.async_register(DOMAIN, "set_tariff", set_tariff, schema=SET_TARIFF_SCHEMA)
    hass.services.async_register(DOMAIN, "replan", replan, schema=REPLAN_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = EmsApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_SITE_ID], entry.data[CONF_TOKEN])
    coord = Ems2Coordinator(hass, entry, api)
    await coord.async_config_entry_first_refresh()
    entry.runtime_data = coord
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
