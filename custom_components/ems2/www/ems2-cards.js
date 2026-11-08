/* EMS 2.0 – zavaděč karet pro dashboard Home Assistantu.
 *
 * Samotné karty („EMS 2.0 – spotřebiče“, „EMS 2.0 – články baterie“) jsou na serveru EMS 2.0
 * (/static/ha/ems2-cards.js) – nová verze karty tak přijde s nasazením serveru, bez aktualizace integrace
 * a restartu HA (stačí obnovit stránku). Když server není dostupný do 4 s, načte se kopie přibalená
 * k integraci (ems2-cards-local.js).
 * Adresu serveru si zavaděč zjistí při každém načtení stránky (/ems2_cards_src – beta „jen sledování“ má
 * přednost), takže po přidání nebo odebrání bety není potřeba restart HA. Když to nejde (starší HA,
 * chyba), použije adresu, kterou doplnila integrace při startu (?srv=…).
 */
(async () => {
  const me = new URL(import.meta.url);
  let srv = (me.searchParams.get("srv") || "").replace(/\/+$/, "");
  const local = new URL("ems2-cards-local.js?v=" + (me.searchParams.get("v") || ""), me).href;
  const timeout = (ms) => new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms));
  try {
    const r = await Promise.race([fetch("/ems2_cards_src", { cache: "no-store" }), timeout(2000)]);
    if (r.ok) {
      const j = await r.json();
      if (j && typeof j.srv === "string") srv = j.srv.replace(/\/+$/, "");
    }
  } catch (e) { /* starší integrace nebo HA – zůstane adresa ze startu */ }
  if (srv) {
    try {
      await Promise.race([import(srv + "/static/ha/ems2-cards.js"), timeout(4000)]);
      window.EMS2_CARDS_SRC = srv;
      return;
    } catch (e) {
      console.warn("EMS 2.0: karty ze serveru se nenačetly (" + e.message + "), použije se kopie z integrace");
    }
  }
  await import(local);
  window.EMS2_CARDS_SRC = "local";
})();
