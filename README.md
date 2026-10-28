# EMS 2.0 – integrace pro Home Assistant

Klient pro server [EMS 2.0](https://ems20.xnas.cz). Posílá serveru měření z domu (FVE, baterie, spotřeba, síť)
a provádí povely, které server spočítá. O baterii rozhoduje jen server, integrace jen měří a přepíná režimy střídače.

Podporované střídače: **SolaX** (přes integraci SolaX Modbus).

## Instalace

**HACS (doporučeno)**

1. HACS → tři tečky → *Vlastní repozitáře* → vlož adresu tohoto repozitáře, typ **Integrace**.
2. Najdi **EMS 2.0**, nainstaluj a restartuj Home Assistant.

**Ručně**

Zkopíruj složku `custom_components/ems2` do `config/custom_components/` a restartuj Home Assistant.

## Nastavení

1. Na webu EMS 2.0 se zaregistruj a počkej na schválení domu.
2. Vyplň sekce **Dům** a **Tarif** a v sekci **Token** si vygeneruj token (ukáže se jen jednou).
3. V HA: *Nastavení → Zařízení a služby → Přidat integraci → EMS 2.0* a zadej:
   - adresu serveru (např. `https://ems20.xnas.cz`),
   - **Dům ID** (např. `dum_7K4PQ2`),
   - token.

## Stín a řízení

- **Stín** (prvních aspoň 7 dní): integrace jen posílá data, server počítá plán a na webu vidíš,
  co by EMS dělalo. Střídače se nedotkne.
- **Řízení** zapneš přepínačem **EMS řídí** (v HA nebo na webu). Jde to po 7 dnech stínu,
  bez mezery v datech delší než 2 h a se 3 slunečnými dny pro kalibraci FVE.

## Režimy

| Režim | Význam |
| --- | --- |
| `self_use` | dům z FVE a baterie (stav bez EMS) |
| `hold` | baterie nevybíjí, dům ze sítě |
| `charge` | nabíjení ze sítě |
| `sell` | prodej z baterie |
| `pv_export` | přebytek FVE do sítě, baterie se nenabíjí |
| `no_export` | nic do sítě |

## Pojistky

- Ve stínu se integrace střídače nedotkne.
- Bez spojení se serverem déle než 10 min nebo po vypršení povelu přepne na `self_use`.
- Nenabíjí nad strop a neprodává pod minimum.
- Hlídá autorepeat (watchdog) a zaseknutí v (R) módu.

## Služba `ems2.set_tariff`

Uloží novou verzi tarifu (platí od `valid_from`). Formát je stejný jako `PUT /tariff`, viz
[docs/API.md](../../docs/API.md).

```yaml
service: ems2.set_tariff
data:
  valid_from: "2026-11-01"
  buy: {mode: spot, markup: 0.40}
  sell: {mode: spot, fee: 0.35}
```

## Testy

```sh
pip install pytest-homeassistant-custom-component   # verze odpovídající tvému HA
python -m pytest
```
