"""Konstanty integrace EMS 2.0."""
from __future__ import annotations

DOMAIN = "ems2"
VERSION = "2.0.16"
DEFAULT_URL = "https://ems20.xnas.cz"
DEFAULT_PREFIX = "solax"

CONF_URL = "url"
CONF_SITE_ID = "site_id"
CONF_TOKEN = "token"
CONF_PREFIX = "prefix"
CONF_GRID_INVERT = "grid_invert"
CONF_ENTITIES = "entities"
CONF_CONTROL = "control"          # "solax" = integrace řídí SolaX, "none" = jen data a doporučení
CONF_BATTERY_INVERT = "battery_invert"
CONTROL_SOLAX = "solax"
CONTROL_NONE = "none"
# režim „jen data a doporučení“: entity, které se dají vybrat (soc povinné)
GENERIC_KEYS = ["soc", "pv_w", "load_w", "grid_w", "battery_w", "grid_l1_w", "grid_l2_w", "grid_l3_w", "pv_today_kwh"]

UPDATE_INTERVAL_S = 5           # telemetrie + povel každých 5 s
INFO_INTERVAL_S = 300           # whoami, nastavení, plán
ACCOUNTING_INTERVAL_S = 900
OFFLINE_FALLBACK_S = 600        # bez spojení déle než 10 min → self_use
BUFFER_MAX = 17280              # max. 1 den měření (po 5 s) k dohnání po výpadku

# klíč telemetrie → výchozí entita (podle integrace SolaX Modbus); {p} = prefix
TELEMETRY_DEFAULTS = {
    "soc": "sensor.{p}_battery_capacity",
    "pv_w": "sensor.{p}_pv_power_total",
    "load_w": "sensor.{p}_house_load",
    "grid_l1_w": "sensor.{p}_measured_power_l1",
    "grid_l2_w": "sensor.{p}_measured_power_l2",
    "grid_l3_w": "sensor.{p}_measured_power_l3",
    "battery_w": "sensor.{p}_battery_power_charge",
    "pv_today_kwh": "sensor.{p}_today_s_solar_energy",
    "inverter_state": "sensor.{p}_run_mode",
}
TELEMETRY_KEYS = list(TELEMETRY_DEFAULTS)

MODE_NAMES = {
    "self_use": "běžný provoz",
    "hold": "šetřit baterii",
    "charge": "nabíjet ze sítě",
    "sell": "prodej z baterie",
    "pv_export": "FVE do sítě",
    "no_export": "nic do sítě",
}
PRICE_LEVELS = ["levná", "běžná", "drahá"]
# příznaky doporučení → binární senzory (klíč, název, ikona)
ADVICE_FLAGS = {
    "charge_from_grid": ("Doporučení: nabíjet ze sítě", "mdi:battery-charging"),
    "discharge_allowed": ("Doporučení: baterie smí vybíjet", "mdi:battery-arrow-down"),
    "sell_from_battery": ("Doporučení: prodávat z baterie", "mdi:cash-plus"),
    "export_allowed": ("Doporučení: dodávka do sítě povolena", "mdi:transmission-tower-export"),
    "cheap_now": ("Levná elektřina teď", "mdi:cash-check"),
    "expensive_now": ("Drahá elektřina teď", "mdi:cash-remove"),
    "negative_buy": ("Záporná cena nákupu", "mdi:cash-minus"),
    "negative_sell": ("Záporná výkupní cena", "mdi:cash-lock"),
    "pv_surplus": ("Přebytek FVE", "mdi:solar-power-variant"),
    "good_time_for_appliances": ("Vhodná chvíle pro spotřebiče", "mdi:washing-machine"),
}
STATE_NAMES = {"pending": "čeká na schválení", "shadow": "zkušební provoz", "control": "řízení", "disabled": "vypnuto"}

# přepínače na serveru → entity v HA
BOOL_SETTINGS = {
    "smart_control": ("Chytré řízení", "mdi:robot"),
    "allow_pv_sell": ("Prodávat přebytek FVE", "mdi:solar-power"),
    "allow_battery_sell": ("Prodávat z baterie", "mdi:battery-arrow-up"),
    "arb_on": ("Nabíjet ze sítě kvůli prodeji", "mdi:transmission-tower-import"),
    "vt_battery_first": ("Ve VT vždy z baterie", "mdi:home-battery"),
    "vt_charge_on": ("Nabíjet ze sítě na drahé hodiny", "mdi:battery-charging"),
    "grid_charge_vt_only": ("Nabíjet ze sítě jen na VT", "mdi:battery-clock"),
    "balancing": ("Balancing", "mdi:scale-balance"),
    "force_balance": ("Vynutit balancing teď", "mdi:flash-alert"),
    "outage_protection": ("Ochrana před výpadkem", "mdi:shield-home"),
    "telegram_notify": ("Upozornění do Telegramu", "mdi:send"),
}
# klíč → (název, min, max, krok, jednotka, ikona)
NUMBER_SETTINGS = {
    "arb_min_profit": ("Min. zisk arbitráže", 0, 20, 0.05, "Kč/kWh", "mdi:cash-plus"),
    "vt_charge_min_gain": ("Min. zisk nabíjení na drahé hodiny", -5, 5, 0.05, "Kč/kWh", "mdi:scale-balance"),
    "grid_charge_max_soc": ("Strop nabíjení ze sítě", 10, 100, 1, "%", "mdi:battery-90"),
    "balancing_interval_days": ("Balancing každých", 1, 90, 1, "d", "mdi:calendar-refresh"),
    "outage_target_soc": ("Ochrana: nabít na", 10, 100, 1, "%", "mdi:battery-charging-high"),
    "outage_hold_soc": ("Ochrana: držet aspoň", 0, 100, 1, "%", "mdi:battery-lock"),
    "outage_lookahead_h": ("Ochrana: připravit předem", 1, 72, 1, "h", "mdi:clock-outline"),
    "manual_power_w": ("Ruční řízení: výkon", 0, 30000, 100, "W", "mdi:flash"),
    "manual_soc": ("Ruční řízení: nabíjet / prodávat do", 5, 100, 1, "%", "mdi:battery-sync"),
}
MANUAL_MODES = {"běžný provoz": "self_use", "šetřit baterii": "hold", "nabíjet ze sítě": "charge",
                "prodej z baterie": "sell", "FVE do sítě": "pv_export", "nic do sítě": "no_export"}
OUTAGE_LEVELS = {"žlutá": 2, "oranžová": 3, "červená": 4}

# vytápění: název v HA → hodnota na serveru
HEATING_MODES = {
    "Nesledovat": "off",
    "Topení smí brát z baterie": "battery",
    "Při topení baterii nevybíjet": "no_battery",
    "Topení ze sítě, zbytek z FVE a baterie": "grid_heater",
}
