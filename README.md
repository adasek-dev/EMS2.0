<p align="center">
  <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/icon-192.png" width="88" alt="EMS 2.0">
</p>

<h1 align="center">EMS 2.0 pro Home Assistant</h1>

<p align="center">
  <b>Baterie, která ví, kdy je elektřina levná.</b><br>
  Každou čtvrthodinu spočítá, kdy nabíjet, kdy šetřit a kdy prodávat – podle vašeho tarifu, spotových cen a předpovědi slunce.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=adasek-dev&repository=EMS2.0&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Otevřít v HACS"></a>
</p>

<p align="center">
  <a href="https://github.com/adasek-dev/EMS2.0/releases"><img src="https://img.shields.io/github/v/release/adasek-dev/EMS2.0?label=verze&color=4f5bd5" alt="Verze"></a>
  <img src="https://img.shields.io/badge/HACS-vlastní%20repozitář-41BDF5" alt="HACS">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.12%2B-18BCF2" alt="Home Assistant">
  <a href="https://ems20.cz"><img src="https://img.shields.io/badge/web-ems20.cz-0f9d74" alt="ems20.cz"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/prehled.webp" alt="Přehled domu v EMS 2.0: tok energie, režim teď a co EMS udělá dál" width="900">
</p>

---

## Proč to zkusit

Střídač sám umí jen „nabij z FVE a vybij do domu“. Neví, že za dvě hodiny bude elektřina dvakrát dražší, že zítra
bude zataženo, ani že se právě vyplatí prodat. **EMS 2.0 to ví** a podle toho střídač řídí.

| Co získáte | Jak |
| --- | --- |
| ⚡ **Levnější elektřina** | Nabíjí ze sítě jen v levných hodinách a baterii šetří na drahé. Spot i fixní tarif, VT/NT podle HDO. |
| ☀️ **Ví, kolik zítra vyrobíte** | Předpověď výroby z počasí pro každou stranu střechy a model spotřeby, který se učí z vašeho domu. |
| 💰 **Prodej ve správnou chvíli** | Přebytek FVE i energie z baterie jde do sítě, když se to opravdu vyplatí. |
| 🔮 **Predikce spotových cen** | Plánuje i dny, které OTE ještě nevyhlásil – a ukazuje, jak přesná predikce byla. |
| 🔋 **Péče o baterii** | Balancing v nejlevnější době, ochrana před výpadkem podle výstrah ČHMÚ, amortizace v ceně každé kWh. |
| 📊 **Všechno na jednom místě** | Webový portál s plánem, rozborem, vyúčtováním a odhadem přeplatku. Funguje i v mobilu. |

## Jak to funguje

```
   🏠 Home Assistant                 ☁️ EMS 2.0                         🏠 Home Assistant
   měření každých 5 s     ──▶     plán na 2–4 dny dopředu      ──▶    povel pro střídač
   (SOC, FVE, síť, dům)           (ceny, počasí, spotřeba)            (SolaX Modbus)
```

Integrace posílá měření a provádí povely. **O baterii rozhoduje server**, takže výpočet je stejně chytrý na
Raspberry Pi jako na výkonném serveru a vylepšení dostanete bez aktualizace.

<p align="center">
  <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/graf.webp" alt="Graf Dnes a zítra: plán nabíjení, prodeje a stav baterie s cenami" width="900">
  <br><sub>Graf „Dnes a zítra“: skutečnost plnou čarou, plán čárkovaně, pás dole ukazuje, co EMS udělá.</sub>
</p>

## Začněte za 10 minut

1. **Zaregistrujte dům** na **[ems20.cz](https://ems20.cz)** a potvrďte e-mail. Dům se rovnou spustí ve zkušebním provozu.
2. **Nainstalujte integraci** – tlačítkem *Otevřít v HACS* nahoře, nebo ručně:
   HACS → ⋮ → *Vlastní repozitáře* → `https://github.com/adasek-dev/EMS2.0`, kategorie **Integrace** → nainstalovat → restart HA.
3. **V portálu** vyplňte dům, baterii a tarif a v sekci *Připojení* si vygenerujte token.
4. **V HA** *Nastavení → Zařízení a služby → Přidat integraci → EMS 2.0* a zadejte adresu serveru, Dům ID a token
   (všechno najdete v portálu v sekci *Připojení*).

Hotovo. Prvních 7 dní běží **zkušební provoz**: EMS počítá plán a v portálu vidíte, co by dělalo a kolik by ušetřilo,
ale **střídače se nedotkne**. Řízení pak zapnete jedním přepínačem *EMS řídí*.

## Co uvidíte

<table>
  <tr>
    <td width="50%"><img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/plan.webp" alt="Plán po hodinách"><br><sub><b>Plán po hodinách</b> – co, kdy a proč. Každou hodinu jde ručně upravit.</sub></td>
    <td width="50%"><img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/rozbor.webp" alt="Rozbor plánu"><br><sub><b>Rozbor</b> – srovnání tarifů, předpověď proti skutečnosti, ideální řízení.</sub></td>
  </tr>
  <tr>
    <td><img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/spot.webp" alt="Spotové ceny"><br><sub><b>Spotové ceny</b> – ceny OTE, predikce na další dny a její úspěšnost.</sub></td>
    <td><img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/billing.webp" alt="Vyúčtování"><br><sub><b>Vyúčtování</b> – náklady k dnešku, zálohy a odhad přeplatku.</sub></td>
  </tr>
</table>

<table>
  <tr>
    <td width="34%"><img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/mobil.webp" alt="EMS 2.0 v telefonu"></td>
    <td>
      <h3>V kapse</h3>
      <p>Portál si přidáte na plochu telefonu jako aplikaci. Vidíte, co dům právě dělá a co EMS chystá dál.</p>
      <ul>
        <li>upozornění na nabíjení ze sítě, prodej a balancing</li>
        <li>souhrn dne a cenové alarmy</li>
        <li>ruční úprava plánu jedním klepnutím</li>
      </ul>
    </td>
  </tr>
</table>

## S čím to funguje

| Systém | Jak |
| --- | --- |
| <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/homeassistant.svg" width="28"> **Home Assistant** | tato integrace – měření, povely a 62 entit s plánem, cenami a doporučením |
| <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/solax-x.png" width="28"> **SolaX** (hybridní střídače Gen4) | řízení přes integraci [SolaX Inverter Modbus](https://github.com/wills106/homeassistant-solax-modbus) |
| 🔌 **Jakýkoli jiný střídač** | režim *Jen data a doporučení*: EMS nic neřídí, vy řídíte automatizacemi podle jeho doporučení |
| <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/nodered.svg" width="28"> **Node-RED** | hotové flow (i přímo přes Modbus, bez HA) – v portálu v *Návodech* |
| <img src="https://raw.githubusercontent.com/adasek-dev/EMS2.0/main/images/mqtt.png" width="28"> **MQTT** | šifrovaně, s HA Discovery – pro vlastní systémy, Shelly, ESP |

## Bezpečně od prvního dne

- **Zkušební provoz** – prvních 7 dní se integrace střídače nedotkne.
- **Bez spojení se serverem** déle než 10 minut nebo po vypršení povelu se střídač vrátí do běžného provozu.
- **Nenabíjí nad strop a nevybíjí pod minimum**, které si nastavíte.
- **Jen dálkové řízení** – nic se nezapisuje do trvalé paměti střídače, každý povel platí desítky sekund.
- **Měření se při výpadku neztratí** – integrace je schová (až na den) a pošle dodatečně.
- **Vaše data jsou vaše** – každý dům má vlastní token a vidí jen svá data.

<details>
<summary><b>Entity v Home Assistantu</b></summary>

| Entita | Co to je |
| --- | --- |
| `switch.ems2_ridi` | **EMS řídí** – zapnutí řízení (po 7 dnech zkušebního provozu) |
| `sensor.ems2_rezim` | režim teď a proč (atributy: povel, co klient opravdu nastavil) |
| `sensor.ems2_plan` | SOC na konci plánu, atribut `slots` = plán po čtvrthodinách pro vlastní grafy |
| `sensor.ems2_cena_nakup`, `sensor.ems2_cena_prodej` | ceny teď |
| `sensor.ems2_naklady_dnes`, `sensor.ems2_uspora_dnes`, `sensor.ems2_vyuctovani` | náklady, úspora, odhad vyúčtování |
| `sensor.ems2_doporuceni`, `sensor.ems2_cenova_hladina`, `sensor.ems2_cil_soc` | doporučený režim, levno/draho, cíl baterie |
| `sensor.ems2_okno_levne_1h` … `_3h` | kdy začíná nejlevnější souvislé okno |
| `sensor.ems2_fve_zbytek_dne`, `…_fve_zitra`, `…_spotreba_zitra` | předpověď výroby a spotřeby |
| `binary_sensor.ems2_dop_cheap_now`, `…_pv_surplus`, `…_good_time_for_appliances` … | příznaky pro automatizace (pračka, bojler, auto) |
| `switch.ems2_balancing`, `…_allow_battery_sell`, `…_outage_protection` … | nastavení serveru přímo z HA |
| `button.ems2_prepocitat` | přepočítat plán hned |

Služby: `ems2.set_tariff`, `ems2.replan`. Všech 62 entit je popsaných v portálu v *Návodech → Entity v HA*.

</details>

<details>
<summary><b>Časté otázky</b></summary>

**Musím mít spotový tarif?** Ne. EMS umí fixní tarif s VT/NT i dynamický a spotový nákup a výkup.

**Co když server vypadne?** Střídač se do 10 minut sám vrátí do běžného provozu, jako by EMS nebylo.

**Můžu si plán upravit?** Ano, v portálu jde každou hodinu ručně přepsat (nabíjet, šetřit, prodat…).

**Mám jiný střídač než SolaX.** Zvolte při nastavení *Jen data a doporučení*. Entity doporučení pak můžete použít
v automatizacích pro svůj střídač.

</details>

---

<p align="center">
  <a href="https://ems20.cz"><b>ems20.cz</b></a> · <a href="https://app.ems20.cz/web/register">Registrace</a> · <a href="https://github.com/adasek-dev/EMS2.0/issues">Nahlásit chybu</a>
</p>
