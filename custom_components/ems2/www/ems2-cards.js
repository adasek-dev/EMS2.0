/* EMS 2.0 – karta „Spotřebiče“ pro dashboard Home Assistantu.
 *
 * Najde sama všechny spotřebiče s plánem (entity sensor.ems2_…spotrebic_<id>_vykon) a pro každý ukáže
 * plánování (nejdřív od, hotovo do, kolikrát, po něm spustit, naplánovat, zrušit) a stav (pustit teď,
 * další běh, dnes hotovo, rádce „nejlevněji“ s dalšími termíny). Bez YAML: Přidat kartu → „EMS 2.0 – spotřebiče“.
 *
 * Volitelná nastavení karty: prefix (např. ems2_beta_ – jen spotřebiče z bety), appliances: [pracka, mycka], title.
 */
(() => {
  const VER = "2.0.35";
  const ICONS = { pracka: "🫧", susicka: "🌀", mycka: "🍽️", auto: "🚗", wall: "🚗", bazen: "🏊" };
  const pad = (n) => String(n).padStart(2, "0");
  const fmtTime = (iso) => { if (!iso) return ""; const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const dayWord = (iso) => {
    if (!iso) return ""; const d = new Date(iso), t = new Date();
    const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()), b = new Date(t.getFullYear(), t.getMonth(), t.getDate());
    const k = Math.round((a - b) / 86400000);
    return k === 0 ? "dnes" : k === 1 ? "zítra" : k === -1 ? "včera" : `${d.getDate()}. ${d.getMonth() + 1}.`;
  };
  const kc = (v) => (v == null ? "" : Number(v).toLocaleString("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " Kč");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  class Ems2AppliancesCard extends HTMLElement {
    setConfig(config) { this._config = config || {}; this._alt = {}; this._render(); }
    static getStubConfig() { return {}; }
    getCardSize() { return 6 * Math.max(1, (this._apps || []).length); }
    getGridOptions() { return { columns: "full", rows: "auto", min_columns: 6 }; }   // sekce: přes celou šířku → spotřebiče vedle sebe
    set hass(hass) {
      this._hass = hass;
      const sig = this._signature();
      if (sig !== this._sig) { this._sig = sig; this._render(); }
    }

    _appliances() {
      const h = this._hass; if (!h) return [];
      const re = /^sensor\.(ems2_(?:[a-z0-9]+_)?)spotrebic_([a-z0-9]+)_vykon$/;
      const found = [];
      for (const id of Object.keys(h.states)) {
        const m = id.match(re); if (!m) continue;
        found.push({ prefix: m[1], id: m[2] });
      }
      let pref = this._config.prefix;
      if (!pref) {                                    // výchozí: hlavní připojení; beta jen když jiné není
        const main = found.filter((x) => x.prefix === "ems2_");
        pref = main.length ? "ems2_" : (found[0] || {}).prefix;
      }
      let out = found.filter((x) => x.prefix === pref);
      if (Array.isArray(this._config.appliances) && this._config.appliances.length) {
        out = this._config.appliances.map((a) => out.find((x) => x.id === a)).filter(Boolean);
      }
      return out;
    }
    _e(a, dom, key) { return `${dom}.${a.prefix}spotrebic_${a.id}_${key}`; }
    _st(a, dom, key) { return this._hass.states[this._e(a, dom, key)]; }
    _signature() {
      const apps = this._appliances();
      return JSON.stringify(apps.map((a) => ["sensor:vykon", "sensor:dalsi", "sensor:dnes", "sensor:nejlevneji", "binary_sensor:pustit",
        "datetime:od", "datetime:do", "number:kolikrat", "select:potom"].map((k) => {
        const [dom, key] = k.split(":"); const s = this._st(a, dom, key);
        return s ? [s.state, s.attributes.schedule ? s.attributes.schedule.length : 0, s.attributes.alternatives ? JSON.stringify(s.attributes.alternatives) : "", (s.attributes.options || []).join(",")] : null;
      })).concat(Object.entries(this._alt || {})));
    }

    _call(domain, service, data) { return this._hass.callService(domain, service, data); }

    _render() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      if (!this._hass) { this.shadowRoot.innerHTML = ""; return; }
      const apps = this._apps = this._appliances();
      const title = this._config.title;
      if (!apps.length) {
        this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty">${title ? `<h2>${esc(title)}</h2>` : ""}Žádné spotřebiče s plánem. Přidej je v EMS 2.0 → Nastavení → Spotřebiče s plánem.</div></ha-card>`;
        return;
      }
      const html = apps.map((a) => this._appHtml(a)).join("");
      this.shadowRoot.innerHTML = `${STYLE}${title ? `<div class="title">${esc(title)}</div>` : ""}<div class="grid">${html}</div>`;
      this._bind(apps);
    }

    _appHtml(a) {
      const p = this._st(a, "sensor", "vykon"); const at = (p && p.attributes) || {};
      const name = at.name || (p && p.attributes.friendly_name || "").replace(/\s*Plánovaný výkon$/, "") || a.id;
      const icon = ICONS[at.icon || ""] || ICONS[a.id] || (/(prač|prac)/i.test(name) ? "🫧" : /(suš|sus)/i.test(name) ? "🌀" : /(myč|myc)/i.test(name) ? "🍽️" : /(aut|wall)/i.test(name) ? "🚗" : "🔌");
      const run = this._st(a, "binary_sensor", "pustit");
      const runNow = run && run.state === "on";
      const next = this._st(a, "sensor", "dalsi"), today = this._st(a, "sensor", "dnes"), best = this._st(a, "sensor", "nejlevneji");
      const od = this._st(a, "datetime", "od"), dd = this._st(a, "datetime", "do"), cnt = this._st(a, "number", "kolikrat"), then = this._st(a, "select", "potom");
      const canPlan = !!(dd && this._st(a, "button", "naplanovat"));
      const split = (s) => { if (!s || !s.state || s.state === "unknown" || s.state === "unavailable") return ["", ""]; const d = new Date(s.state.replace(" ", "T")); return [`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, `${pad(d.getHours())}:${pad(d.getMinutes())}`]; };
      const [odD, odT] = split(od), [doD, doT] = split(dd);
      // rádce: nejlevnější termín a další (tlačítko „jiný termín“ jimi prochází)
      const alts = ((best && best.attributes.alternatives) || []);
      const k = Math.min(this._alt[a.id] || 0, Math.max(0, alts.length - 1));
      const al = alts[k];
      const nowKc = best && best.attributes.now_kc;
      const soon = al && new Date(al.start) - Date.now() < 15 * 60000;
      const night = al && ((h) => h >= 22 || h < 6)(new Date(al.start).getHours());
      const bestTxt = al ? `${k === 0 ? "Nejlevněji" : `${k + 1}. nejlevnější`} ${soon ? "hned teď" : `${dayWord(al.start)} ${fmtTime(al.start)}–${fmtTime(al.end)}`}${night && !soon ? " 🌙" : ""}` : "";
      const bestSub = al ? `≈ ${kc(al.kc)}${nowKc != null && nowKc > al.kc + 0.05 && !soon ? ` · teď by to stálo ${kc(nowKc)}` : ""}` : "";
      const pill = runNow ? `<span class="pill run">● pusť teď${at.run_until ? ` do ${fmtTime(at.run_until)}` : ""}</span>`
        : (next && next.state && next.state !== "unknown" && next.state !== "unavailable") ? `<span class="pill">další ${dayWord(next.state)} ${fmtTime(next.state)}</span>`
        : `<span class="pill idle">nic naplánováno</span>`;
      const opts = then ? (then.attributes.options || []) : [];
      return `
      <ha-card class="app" data-app="${a.id}">
        <div class="head"><span class="ic">${icon}</span><div><div class="nm">${esc(name)}</div>
          <div class="sub">${at.nominal_w ? (at.nominal_w / 1000).toLocaleString("cs-CZ", { maximumFractionDigits: 1 }) + " kW · " : ""}${at.minutes ? (at.minutes / 60).toLocaleString("cs-CZ", { maximumFractionDigits: 1 }) + " h · " : ""}${at.control ? "spíná EMS" : "připomene"}</div></div>${pill}</div>
        <div class="stat">
          <div><span>Další běh</span><b>${next && next.state && next.state !== "unknown" && next.state !== "unavailable" ? `${dayWord(next.state)} ${fmtTime(next.state)}${(next.attributes || {}).next_end ? "–" + fmtTime(next.attributes.next_end) : ""}` : "–"}</b></div>
          <div><span>Dnes hotovo</span><b>${today && today.state !== "unknown" ? esc(today.state) : "–"}</b></div>
        </div>
        ${al ? `<div class="best"><div>💡 <b>${bestTxt}</b><small>${bestSub}</small></div>
          <div class="best-act">${canPlan ? `<button class="link" data-act="here">Naplánovat sem</button>` : ""}${alts.length > 1 ? `<button class="link" data-act="other">jiný termín ›</button>` : ""}</div></div>` : ""}
        ${canPlan ? `
        <div class="form">
          <div class="f full"><label>Hotovo do</label><div class="dt"><input type="date" data-f="do-d" value="${doD}"><input type="time" data-f="do-t" value="${doT}"></div></div>
          <div class="f full"><label>Nejdřív od</label><div class="dt"><input type="date" data-f="od-d" value="${odD}"><input type="time" data-f="od-t" value="${odT}"></div></div>
          <div class="f"><label>Kolikrát</label><div class="cnt"><button data-act="minus" aria-label="Méně">−</button><span>${cnt ? Math.round(Number(cnt.state) || 1) : 1}</span><button data-act="plus" aria-label="Více">+</button></div></div>
          ${opts.length > 1 ? `<div class="f"><label>Po něm spustit</label><select data-f="then">${opts.map((o) => `<option ${then && then.state === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>` : ""}
        </div>
        <div class="btns"><button class="pri" data-act="plan">Naplánovat</button><button class="sec" data-act="cancel">Zrušit další</button></div>` : ""}
      </ha-card>`;
    }

    _bind(apps) {
      const root = this.shadowRoot;
      for (const a of apps) {
        const el = root.querySelector(`[data-app="${a.id}"]`); if (!el) continue;
        const q = (s) => el.querySelector(s);
        const setDT = (key, dSel, tSel) => {
          const d = q(dSel).value, t = q(tSel).value; if (!d || !t) return;
          this._call("datetime", "set_value", { entity_id: this._e(a, "datetime", key), datetime: `${d} ${t}:00` });
        };
        el.querySelectorAll("[data-f]").forEach((inp) => inp.addEventListener("change", () => {
          const f = inp.dataset.f;
          if (f.startsWith("od")) setDT("od", '[data-f="od-d"]', '[data-f="od-t"]');
          else if (f.startsWith("do")) setDT("do", '[data-f="do-d"]', '[data-f="do-t"]');
          else if (f === "then") this._call("select", "select_option", { entity_id: this._e(a, "select", "potom"), option: inp.value });
        }));
        el.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
          const act = b.dataset.act;
          const cnt = this._st(a, "number", "kolikrat");
          const n = cnt ? Math.round(Number(cnt.state) || 1) : 1;
          if (act === "plus" || act === "minus") {
            this._call("number", "set_value", { entity_id: this._e(a, "number", "kolikrat"), value: Math.max(1, Math.min(8, n + (act === "plus" ? 1 : -1))) });
          } else if (act === "plan") {
            b.disabled = true; b.textContent = "Plánuji…";
            try { await this._call("button", "press", { entity_id: this._e(a, "button", "naplanovat") }); b.textContent = "✓ Naplánováno"; }
            catch (e) { b.textContent = "Chyba"; }
            setTimeout(() => this._render(), 1500);
          } else if (act === "cancel") {
            await this._call("button", "press", { entity_id: this._e(a, "button", "zrusit") });
          } else if (act === "other") {
            const best = this._st(a, "sensor", "nejlevneji"); const n2 = ((best && best.attributes.alternatives) || []).length;
            this._alt[a.id] = ((this._alt[a.id] || 0) + 1) % Math.max(1, n2); this._sig = null; this._render();
          } else if (act === "here") {
            // termín z rádce: okno přesně kolem něj a naplánovat
            const best = this._st(a, "sensor", "nejlevneji"); const alts = (best && best.attributes.alternatives) || [];
            const al = alts[Math.min(this._alt[a.id] || 0, alts.length - 1)]; if (!al) return;
            const loc = (iso) => { const d = new Date(iso); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:00`; };
            b.disabled = true;
            await this._call("datetime", "set_value", { entity_id: this._e(a, "datetime", "od"), datetime: loc(al.start) });
            await this._call("datetime", "set_value", { entity_id: this._e(a, "datetime", "do"), datetime: loc(al.end) });
            await this._call("button", "press", { entity_id: this._e(a, "button", "naplanovat") });
            b.textContent = "✓ Naplánováno"; setTimeout(() => this._render(), 1500);
          }
        }));
      }
    }
  }

  const STYLE = `<style>
    :host { display: block; }
    .title { font-size: 20px; margin: 4px 4px 10px; color: var(--primary-text-color); }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
    ha-card { padding: 14px 16px 16px; display: block; color: var(--primary-text-color); }
    .empty { padding: 16px; color: var(--secondary-text-color); }
    .head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
    .head .ic { font-size: 26px; width: 42px; height: 42px; display: grid; place-items: center; border-radius: 12px;
      background: var(--secondary-background-color, rgba(127,127,127,.12)); flex: none; }
    .head > div { flex: 1; min-width: 0; }
    .nm { font-size: 18px; font-weight: 500; color: var(--primary-text-color); }
    .sub { font-size: 12px; color: var(--secondary-text-color); }
    .pill { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 99px; white-space: nowrap;
      background: rgba(99,102,241,.16); color: var(--primary-color); }
    .pill.run { background: rgba(16,185,129,.16); color: #10b981; }
    .pill.idle { background: var(--secondary-background-color, rgba(127,127,127,.12)); color: var(--secondary-text-color); }
    .stat { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 4px 0 10px; }
    .stat > div { background: var(--secondary-background-color, rgba(127,127,127,.08)); border-radius: 10px; padding: 8px 10px; }
    .stat span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .stat b { font-size: 15px; font-weight: 500; color: var(--primary-text-color); }
    .best { border: 1px solid var(--divider-color, rgba(127,127,127,.25)); border-radius: 10px; padding: 8px 10px; margin-bottom: 12px; }
    .best b { font-weight: 500; } .best small { display: block; font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
    .best-act { display: flex; gap: 14px; margin-top: 6px; }
    .link { background: none; border: 0; padding: 0; font: inherit; font-size: 13px; font-weight: 600; color: var(--primary-color); cursor: pointer; }
    .form { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; margin-bottom: 12px; }
    .form label { font-size: 12px; color: var(--secondary-text-color); margin-top: 6px; }
    .form .f { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
    .form .f.full { grid-column: 1 / -1; }
    .dt { display: grid; grid-template-columns: 1.5fr 1fr; gap: 6px; }
    input, select { font: inherit; font-size: 15px; color: var(--primary-text-color); background: var(--secondary-background-color, rgba(127,127,127,.12));
      border: 0; border-bottom: 1px solid var(--divider-color, #888); border-radius: 6px 6px 0 0; padding: 8px; min-width: 0; width: 100%; box-sizing: border-box;
      color-scheme: light dark; }
    .cnt { display: inline-flex; align-items: center; gap: 0; align-self: flex-start; border-radius: 10px; overflow: hidden;
      background: var(--secondary-background-color, rgba(127,127,127,.12)); }
    .cnt button { width: 42px; height: 38px; border: 0; background: none; font-size: 22px; color: var(--primary-color); cursor: pointer; }
    .cnt span { min-width: 34px; text-align: center; font-size: 17px; color: var(--primary-text-color); }
    .btns { display: grid; grid-template-columns: 1.4fr 1fr; gap: 8px; }
    .btns button { height: 46px; border-radius: 12px; font: inherit; font-size: 15px; font-weight: 600; cursor: pointer; border: 0; }
    .pri { background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .sec { background: none; color: var(--primary-text-color); border: 1px solid var(--divider-color, rgba(127,127,127,.4)) !important; }
    button:disabled { opacity: .7; }
  </style>`;

  if (!customElements.get("ems2-appliances-card")) customElements.define("ems2-appliances-card", Ems2AppliancesCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.find((c) => c.type === "ems2-appliances-card")) {
    window.customCards.push({ type: "ems2-appliances-card", name: "EMS 2.0 – spotřebiče",
      description: "Plánování pračky, myčky, sušičky… z EMS 2.0 – karta se sama naplní všemi spotřebiči.", preview: true });
  }

  /* ── karta „EMS 2.0 – články baterie“ (monitor Solax T58 v integraci) ─────────────────────────── */
  const num = (v, d) => (v == null ? "–" : Number(v).toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d }));
  class Ems2BatteryCard extends HTMLElement {
    setConfig(config) { this._config = config || {}; this._render(); }
    static getStubConfig() { return {}; }
    getCardSize() { return 8; }
    getGridOptions() { return { columns: "full", rows: "auto", min_columns: 6 }; }   // sekce: přes celou šířku
    // živá data přímo z integrace (websocket) každých 5 s – do historie HA se nic nezapisuje; entita je záloha
    connectedCallback() { this._poll(); this._timer = setInterval(() => this._poll(), (this._config && this._config.refresh_s || 5) * 1000); }
    disconnectedCallback() { clearInterval(this._timer); }
    _poll() {
      if (!this._hass || !this._hass.callWS || this._busy) return;
      this._busy = true;
      this._hass.callWS({ type: "ems2/cells" }).then((r) => { this._ws = r; this._wsAt = Date.now(); this._render(); })
        .catch(() => { this._ws = null; }).finally(() => { this._busy = false; });
    }
    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) this._poll();
      if (this._ws) return;
      const st = this._state();
      const sig = st ? st.last_updated + st.state : "none";
      if (sig !== this._sig) { this._sig = sig; this._render(); }
    }
    _state() {
      const h = this._hass; if (!h) return null;
      const id = this._config.entity || (h.states["sensor.ems2_baterie_clanky"] ? "sensor.ems2_baterie_clanky"
        : Object.keys(h.states).find((k) => /^sensor\.ems2_[a-z0-9]+_baterie_clanky$/.test(k)));
      return id ? h.states[id] : null;
    }
    _render() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      const ws = this._ws && this._ws.configured ? this._ws : null;
      const st = ws ? { attributes: ws, last_updated: new Date(this._wsAt).toISOString() } : this._state();
      const title = esc(this._config.title || "Baterie – články");
      if (ws && ws.premium === false) {
        this.shadowRoot.innerHTML = `${BCSS}<ha-card><div class="hd"><b>${title}</b><span class="pill warn">Premium</span></div><p class="mut">Monitor článků baterie je součástí Premium. Zapíná ho správce EMS 2.0 u domu.</p></ha-card>`;
        return;
      }
      if (!st) {
        this.shadowRoot.innerHTML = `${BCSS}<ha-card><div class="hd"><b>${title}</b></div><p class="mut">Monitor článků není nastavený: Nastavení → Zařízení a služby → EMS 2.0 → Konfigurovat → Monitor článků baterie.</p></ha-card>`;
        return;
      }
      const a = st.attributes || {}, mods = a.modules || [];
      if (!mods.length) {
        this.shadowRoot.innerHTML = `${BCSS}<ha-card><div class="hd"><b>${title}</b><span class="pill warn">bez dat</span></div><p class="mut">${esc(a.error || "Čekám na data ze sběrnice baterií…")} (${esc(a.source || "")})</p></ha-card>`;
        return;
      }
      let gx = -1, gn = 99, worst = null, low = null, hot = null, nbal = 0, nc = 0;
      for (const m of mods) {
        nc = Math.max(nc, m.cells.length);
        nbal += (m.balancing || []).length;
        m.cells.forEach((c, i) => { if (c == null) return; if (c > gx) gx = c; if (c < gn) { gn = c; low = { m, i }; } });
        if (!worst || (m.delta_mv || 0) > (worst.delta_mv || 0)) worst = m;
        if (m.temp_max != null && (!hot || m.temp_max > hot.temp_max)) hot = m;
      }
      const lim = this._config.warn_mv || 40;
      const lvl = worst.delta_mv >= lim * 1.5 ? ["bad", "problém"] : worst.delta_mv >= lim ? ["warn", "pozor"] : ["ok", "v pořádku"];
      const packs = new Set(mods.map((m) => m.pack)).size, per = Math.max(...mods.map((m) => m.mod));
      let rows = "";
      for (const m of mods) {
        const vals = m.cells.filter((c) => c != null), mx = Math.max(...vals), mn = Math.min(...vals), bal = new Set(m.balancing || []);
        let tds = "";
        for (let i = 0; i < nc; i++) {
          const c = m.cells[i];
          let cls = c == null ? "" : c === gx ? "gx" : c === gn ? "gn" : mx !== mn && c === mx ? "x" : mx !== mn && c === mn ? "n" : "";
          if (bal.has(i + 1)) cls += " b";
          tds += `<td class="${cls}">${c == null ? "–" : num(c, 3)}</td>`;
        }
        const t = m.temp_min != null ? `${num(m.temp_min, 0)}–${num(m.temp_max, 0)}` : "–";
        rows += `<tr><th>${m.pack}·M${m.mod}</th>${tds}<td class="s${m.delta_mv >= lim ? " w" : ""}">${num(m.delta_mv, 0)}</td><td class="s">${t}</td><td class="s">${num(m.soc, 0)} %</td></tr>`;
      }
      const ago = ws ? 0 : Math.max(0, Math.round((Date.now() - new Date(st.last_updated)) / 1000));
      this.shadowRoot.innerHTML = `${BCSS}<ha-card>
        <div class="hd"><span class="ic">🔋</span><b>${title}</b><span class="pill ${lvl[0]}">${lvl[1]}</span></div>
        <div class="sub">Solax T58 · ${packs} ${packs === 1 ? "pack" : packs < 5 ? "packy" : "packů"} × ${per} ${per === 1 ? "modul" : per < 5 ? "moduly" : "modulů"} · ${nc} článků · ${ws ? "živě" : "před " + (ago < 90 ? ago + " s" : Math.round(ago / 60) + " min")}</div>
        <div class="stats">
          <div><b>${num(worst.delta_mv, 0)} <small>mV</small></b><span>největší rozdíl<br>pack ${worst.pack} · M${worst.mod}</span></div>
          <div><b>${num(gn, 3)} <small>V</small></b><span>nejnižší článek<br>${low.m.pack} · M${low.m.mod} · č. ${low.i + 1}</span></div>
          <div><b>${hot ? num(Math.min(...mods.map((m) => m.temp_min ?? 99)), 0) + "–" + num(hot.temp_max, 0) : "–"} <small>°C</small></b><span>teploty<br>${hot ? `nejteplejší ${hot.pack} · M${hot.mod}` : ""}</span></div>
          <div><b>${nbal}</b><span>${nbal === 1 ? "článek" : nbal > 1 && nbal < 5 ? "články" : "článků"}<br>${nbal > 1 && nbal < 5 ? "balancují" : "balancuje"}</span></div>
        </div>
        <div class="wrap"><table><thead><tr><th></th>${Array.from({ length: nc }, (_, i) => `<th>${i + 1}</th>`).join("")}<th>Δ mV</th><th>°C</th><th>SOC</th></tr></thead><tbody>${rows}</tbody></table></div>
        <div class="leg"><span><i class="x"></i>nejvyšší v modulu</span><span><i class="n"></i>nejnižší v modulu</span><span><i class="gx"></i>nejvyšší celkem</span><span><i class="gn"></i>nejnižší celkem</span><span><i class="b"></i>balancuje</span></div>
      </ha-card>`;
    }
  }
  const BCSS = `<style>
    ha-card { padding: 16px; }
    .hd { display: flex; align-items: center; gap: 10px; font-size: 18px; }
    .ic { font-size: 20px; }
    .sub, .mut { color: var(--secondary-text-color); font-size: 13px; margin: 4px 0 12px; }
    .pill { margin-left: auto; font-size: 12px; border-radius: 99px; padding: 2px 10px; font-weight: 600; }
    .pill.ok { background: rgba(46,204,113,.18); color: #2ecc71; } .pill.warn { background: rgba(243,156,18,.2); color: #f39c12; }
    .pill.bad { background: rgba(231,76,60,.2); color: #e74c3c; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
    .stats div { background: var(--secondary-background-color, rgba(127,127,127,.12)); border-radius: 10px; padding: 10px 12px; }
    .stats b { font-size: 20px; display: block; } .stats small { font-size: 12px; color: var(--secondary-text-color); }
    .stats span { font-size: 12px; color: var(--secondary-text-color); }
    .wrap { overflow-x: auto; }
    table { border-collapse: separate; border-spacing: 2px; font-size: 12px; font-variant-numeric: tabular-nums; width: 100%; min-width: 760px; }
    th { color: var(--secondary-text-color); font-weight: 500; font-size: 11px; padding: 3px; }
    tbody th { color: var(--primary-text-color); white-space: nowrap; text-align: left; }
    td { background: var(--secondary-background-color, rgba(127,127,127,.12)); border-radius: 5px; text-align: center; padding: 5px 1px; }
    td.x { background: rgba(231,76,60,.22); color: #e74c3c; } td.n { background: rgba(52,120,246,.22); color: #5b8def; }
    td.gx { background: #c0392b; color: #fff; font-weight: 700; } td.gn { background: #2f6fe8; color: #fff; font-weight: 700; }
    td.b { box-shadow: inset 0 0 0 2px #2ecc71; } td.s { background: none; white-space: nowrap; font-weight: 600; padding: 5px 6px; }
    td.s.w { color: #f39c12; }
    .leg { display: flex; flex-wrap: wrap; gap: 6px 14px; color: var(--secondary-text-color); font-size: 12px; margin-top: 10px; }
    .leg i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
    .leg i.x { background: rgba(231,76,60,.22); } .leg i.n { background: rgba(52,120,246,.22); } .leg i.gx { background: #c0392b; }
    .leg i.gn { background: #2f6fe8; } .leg i.b { box-shadow: inset 0 0 0 2px #2ecc71; }
    @media (max-width: 600px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  </style>`;
  if (!customElements.get("ems2-battery-card")) customElements.define("ems2-battery-card", Ems2BatteryCard);
  if (!window.customCards.find((c) => c.type === "ems2-battery-card")) {
    window.customCards.push({ type: "ems2-battery-card", name: "EMS 2.0 – články baterie",
      description: "Napětí všech článků, rozdíly, teploty a balancování z monitoru baterie Solax T58.", preview: true });
  }
  console.info(`%c EMS 2.0 %c karty ${VER} `, "background:#10b981;color:#fff;border-radius:3px 0 0 3px;padding:1px 4px", "background:#334155;color:#fff;border-radius:0 3px 3px 0;padding:1px 4px");
})();
