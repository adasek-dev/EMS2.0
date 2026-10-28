"""Průvodce nastavením: server + Dům ID + token → SolaX → (volitelně) údaje o domu."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EmsApi, EmsApiError, EmsAuthError
from .const import (CONF_ENTITIES, CONF_GRID_INVERT, CONF_PREFIX, CONF_SITE_ID, CONF_TOKEN, CONF_URL, DEFAULT_PREFIX,
                    DEFAULT_URL, DOMAIN, TELEMETRY_DEFAULTS, TELEMETRY_KEYS)

_LOGGER = logging.getLogger(__name__)


async def _check(hass, url: str, site_id: str, token: str) -> tuple[dict | None, str | None]:
    api = EmsApi(async_get_clientsession(hass), url, site_id, token)
    try:
        return await api.whoami(), None
    except EmsAuthError:
        return None, "invalid_auth"
    except EmsApiError as e:
        return None, "cannot_connect" if e.status == 0 else "unknown"


class Ems2ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._whoami: dict = {}

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_SITE_ID] = user_input[CONF_SITE_ID].strip()
            info, err = await _check(self.hass, user_input[CONF_URL], user_input[CONF_SITE_ID], user_input[CONF_TOKEN])
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(info["site_id"])
                self._abort_if_unique_id_configured()
                self._data.update(user_input)
                self._whoami = info
                return await self.async_step_inverter()
        schema = vol.Schema({
            vol.Required(CONF_URL, default=DEFAULT_URL): str,
            vol.Required(CONF_SITE_ID): str,
            vol.Required(CONF_TOKEN): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_inverter(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            prefix = user_input[CONF_PREFIX].strip()
            if self.hass.states.get(TELEMETRY_DEFAULTS["soc"].format(p=prefix)) is None:
                errors[CONF_PREFIX] = "entity_missing"
            else:
                self._data.update({CONF_PREFIX: prefix, CONF_GRID_INVERT: user_input.get(CONF_GRID_INVERT, False)})
                api = EmsApi(async_get_clientsession(self.hass), self._data[CONF_URL], self._data[CONF_SITE_ID],
                             self._data[CONF_TOKEN])
                try:
                    cfg = (await api.config()).get("config", {})
                except EmsApiError:
                    cfg = {}
                if not cfg.get("pv_arrays"):
                    return await self.async_step_house()
                return self._create()
        schema = vol.Schema({
            vol.Required(CONF_PREFIX, default=DEFAULT_PREFIX): str,
            vol.Optional(CONF_GRID_INVERT, default=False): bool,
        })
        return self.async_show_form(step_id="inverter", data_schema=schema, errors=errors,
                                    description_placeholders={"site": self._whoami.get("name", "")})

    async def async_step_house(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            arrays = []
            for i in (1, 2):
                if user_input.get(f"pv{i}_kwp"):
                    arrays.append({"name": f"pole {i}", "tilt": user_input.get(f"pv{i}_tilt", 35),
                                   "azimuth": user_input.get(f"pv{i}_azimuth", 0), "kwp": user_input[f"pv{i}_kwp"]})
            cfg = {
                "site": {"lat": user_input["lat"], "lon": user_input["lon"]},
                "battery": {"capacity_kwh": user_input["capacity_kwh"], "min_soc": int(user_input["min_soc"]),
                            "max_charge_w": int(user_input["max_charge_w"]),
                            "max_discharge_w": int(user_input["max_discharge_w"]),
                            "max_sell_w": int(user_input["max_discharge_w"])},
                "pv_arrays": arrays,
                "grid": {"breaker_a": int(user_input["breaker_a"])},
            }
            api = EmsApi(async_get_clientsession(self.hass), self._data[CONF_URL], self._data[CONF_SITE_ID],
                         self._data[CONF_TOKEN])
            try:
                await api.put_config(cfg)
                return self._create()
            except EmsApiError as e:
                _LOGGER.warning("EMS 2.0 config: %s %s", e.message, e.problems)
                errors["base"] = "invalid_config"
        def num(mn, mx, step, unit=None):
            cfg = {"min": mn, "max": mx, "step": step, "mode": selector.NumberSelectorMode.BOX}
            if unit:
                cfg["unit_of_measurement"] = unit
            return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))
        schema = vol.Schema({
            vol.Required("lat", default=self.hass.config.latitude): num(-90, 90, "any"),
            vol.Required("lon", default=self.hass.config.longitude): num(-180, 180, "any"),
            vol.Required("capacity_kwh", default=10.0): num(0.5, 500, 0.1, "kWh"),
            vol.Required("min_soc", default=20): num(0, 90, 1, "%"),
            vol.Required("max_charge_w", default=5000): num(100, 100000, 100, "W"),
            vol.Required("max_discharge_w", default=5000): num(100, 100000, 100, "W"),
            vol.Required("breaker_a", default=25): num(6, 250, 1, "A"),
            vol.Optional("pv1_kwp"): num(0, 1000, "any", "kWp"),
            vol.Optional("pv1_tilt", default=35): num(0, 90, 1, "°"),
            vol.Optional("pv1_azimuth", default=0): num(-180, 180, "any", "°"),
            vol.Optional("pv2_kwp"): num(0, 1000, "any", "kWp"),
            vol.Optional("pv2_tilt", default=35): num(0, 90, 1, "°"),
            vol.Optional("pv2_azimuth", default=0): num(-180, 180, "any", "°"),
        })
        return self.async_show_form(step_id="house", data_schema=schema, errors=errors)

    def _create(self) -> ConfigFlowResult:
        return self.async_create_entry(title=f"EMS 2.0 – {self._whoami.get('name', self._data[CONF_SITE_ID])}",
                                       data=self._data)

    async def async_step_reauth(self, entry_data: dict) -> ConfigFlowResult:
        self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            _, err = await _check(self.hass, self._data[CONF_URL], self._data[CONF_SITE_ID], user_input[CONF_TOKEN])
            if err:
                errors["base"] = err
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(entry, data={**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]})
        schema = vol.Schema({vol.Required(CONF_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors,
                                    description_placeholders={"site": self._data.get(CONF_SITE_ID, "")})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return Ems2OptionsFlow()


class Ems2OptionsFlow(OptionsFlow):
    """Vlastní entity pro měření (když se liší od výchozích entit SolaX Modbus)."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        opts = {**self.config_entry.data, **self.config_entry.options}
        prefix = opts.get(CONF_PREFIX) or DEFAULT_PREFIX
        current = opts.get(CONF_ENTITIES) or {}
        if user_input is not None:
            ents = {k: user_input[k] for k in TELEMETRY_KEYS if user_input.get(k)}
            return self.async_create_entry(data={CONF_PREFIX: user_input.get(CONF_PREFIX, prefix),
                                                 CONF_GRID_INVERT: user_input.get(CONF_GRID_INVERT, False),
                                                 CONF_ENTITIES: ents})
        fields: dict = {
            vol.Required(CONF_PREFIX, default=prefix): str,
            vol.Optional(CONF_GRID_INVERT, default=opts.get(CONF_GRID_INVERT, False)): bool,
        }
        for k in TELEMETRY_KEYS:
            default = current.get(k) or TELEMETRY_DEFAULTS[k].format(p=prefix)
            fields[vol.Optional(k, description={"suggested_value": default})] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
