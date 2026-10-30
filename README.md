# EMS 2.0 – integrace pro Home Assistant

Klient pro server [EMS 2.0](https://ems20.cz). Posílá serveru měření z domu (FVE, baterie, spotřeba, síť)
a provádí povely, které server spočítá a odešle zpět klientovi. O baterii rozhoduje jen server, integrace jen měří a přepíná režimy střídače.

Integrace vyžaduje pro řízení integraci z https://github.com/wills106/homeassistant-solax-modbus

Podporované střídače: **SolaX** (přes integraci SolaX Modbus).
Veškeré řízení střídače je řízeno pouze přes remote control a proto nezapisuje do EEPROM!

<img width="1881" height="823" alt="{34D4E253-915D-4C61-87F2-E9755C834A82}" src="https://github.com/user-attachments/assets/5a6f591c-2499-4f82-b419-c6bcd8b1836c" />

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

## Učení a řízení

- **Učení** (prvních aspoň 7 dní): integrace jen posílá data, server počítá plán a na webu vidíš,
  co by EMS dělalo. Střídače se to nijak nedotkne.
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

<img width="1880" height="784" alt="{A0C6B53E-0716-49AF-89F3-451DC2927CEE}" src="https://github.com/user-attachments/assets/a4d72326-a208-418c-b34a-c725bdb16f41" />

<img width="1658" height="911" alt="{35D20215-4B56-4EE5-ABEF-98722F03E455}" src="https://github.com/user-attachments/assets/74ded836-ad1b-4833-bf8f-1025bdc3f3da" />



## Pojistky

- V režimu učení se integrace střídače nedotkne.
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
