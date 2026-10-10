"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const PAGE = 300;           // kerralla piirrettävät rivit
  const POLL_MS = 700;
  const MAX_POLL_FAILS = 5;
  const KIND_LABEL = { video: "Video", short: "Short", live: "Livelähetys" };

  const el = {
    form: $("form"), url: $("url"), collect: $("collect"), cancel: $("cancel"),
    kVideo: $("k-video"), kShort: $("k-short"), kLive: $("k-live"),
    mLinks: $("m-links"), mDetails: $("m-details"), exact: $("exact"), limit: $("limit"),
    progress: $("progress"), status: $("status"), count: $("count"),
    banner: $("banner"), bannerText: $("banner-text"), retry: $("retry"),
    filter: $("filter"), kindFilter: $("kind-filter"), sort: $("sort"),
    table: $("table"), rows: $("rows"), empty: $("empty"), more: $("more"),
    copy: $("copy"), txt: $("txt"), csv: $("csv"), open: $("open"),
  };

  const state = {
    videos: [], byId: new Map(), jobId: null, running: false, timer: null, fails: 0,
    after: 0, uafter: 0, lastRequest: null, channel: "", selectedId: null, shown: PAGE, visible: [],
  };

  // ---------- apufunktiot ----------
  const norm = (s) => (s || "").normalize("NFC").toLocaleLowerCase("fi");
  const fmtDur = (s) => {
    if (s == null) return "";
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
  };
  const selectedKinds = () => [["video", el.kVideo], ["short", el.kShort], ["live", el.kLive]]
    .filter(([, cb]) => cb.checked).map(([k]) => k);
  const linksOnly = () => el.mLinks.checked;

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* ei JSON-vastausta */ }
    return { ok: res.ok, status: res.status, data };
  }

  // ---------- käyttöliittymän tila ----------
  function showBanner(text, level) {
    el.bannerText.textContent = text;
    el.banner.className = "banner" + (level === "warn" ? " warn" : "");
    el.banner.hidden = false;
  }
  function hideBanner() { el.banner.hidden = true; }

  function updateControls() {
    const running = state.running;
    el.collect.disabled = running || selectedKinds().length === 0;
    el.cancel.disabled = !running;
    for (const x of [el.url, el.kVideo, el.kShort, el.kLive, el.mLinks, el.mDetails, el.limit]) x.disabled = running;
    el.exact.disabled = running || linksOnly();
    if (linksOnly()) el.exact.checked = false;
    el.retry.disabled = running || !state.lastRequest;
    el.progress.classList.toggle("busy", running);
    const has = state.visible.length > 0;
    el.copy.disabled = el.txt.disabled = el.csv.disabled = !has;
    el.open.disabled = !(state.selectedId && state.byId.has(state.selectedId));
    el.table.classList.toggle("links", linksOnly());
    el.table.classList.toggle("details", !linksOnly());
    const total = state.videos.length, shown = state.visible.length;
    el.count.textContent = "Löydetty: " + total + (shown !== total ? ` (näkyvissä ${shown})` : "");
  }

  // ---------- suodatus, järjestys, piirto ----------
  function computeVisible() {
    const terms = norm(el.filter.value).split(/\s+/).filter(Boolean);
    const kind = el.kindFilter.value;
    let list = state.videos.filter((v) => (!kind || v.kind === kind) && terms.every((t) => norm(v.title).includes(t)));
    const s = el.sort.value;
    if (s === "title") list = [...list].sort((a, b) => a.title.localeCompare(b.title, "fi"));
    else if (s === "date-desc" || s === "date-asc") {
      const dir = s === "date-desc" ? -1 : 1;
      list = [...list].sort((a, b) => {
        if (!a.date !== !b.date) return a.date ? -1 : 1;  // päivättömät aina loppuun
        return a.date < b.date ? -dir : a.date > b.date ? dir : 0;
      });
    } else if (s === "dur-desc") list = [...list].sort((a, b) => (b.duration ?? -1) - (a.duration ?? -1));
    state.visible = list;
  }

  function td(cls, text) { const c = document.createElement("td"); c.className = cls; c.textContent = text; return c; }

  function makeRow(v) {
    const tr = document.createElement("tr");
    tr.dataset.id = v.id;
    tr.tabIndex = 0;
    tr.setAttribute("aria-selected", String(v.id === state.selectedId));
    tr.append(td("c-title", v.title || "(ei otsikkoa)"));
    const urlCell = document.createElement("td");
    urlCell.className = "c-url";
    const a = document.createElement("a");
    a.href = v.url; a.textContent = v.url; a.target = "_blank"; a.rel = "noopener noreferrer";
    urlCell.append(a);
    tr.append(urlCell, td("c-date", v.date || "–"), td("c-dur", fmtDur(v.duration)),
      td("c-kind", KIND_LABEL[v.kind] || ""), td("c-channel", v.channel || ""));
    return tr;
  }

  function render() {
    computeVisible();
    const frag = document.createDocumentFragment();
    for (const v of state.visible.slice(0, state.shown)) frag.append(makeRow(v));
    el.rows.replaceChildren(frag);
    el.empty.hidden = state.visible.length > 0;
    el.more.hidden = state.visible.length <= state.shown;
    if (!el.more.hidden) el.more.textContent = `Näytä lisää (${state.visible.length - state.shown})`;
    updateControls();
  }

  function selectRow(id) {
    state.selectedId = id;
    for (const tr of el.rows.children) tr.setAttribute("aria-selected", String(tr.dataset.id === id));
    updateControls();
  }

  // ---------- haku ----------
  function currentRequest() {
    return {
      url: el.url.value.trim(), kinds: selectedKinds(),
      exact_dates: el.exact.checked && !linksOnly(), limit: Math.max(0, parseInt(el.limit.value, 10) || 0),
    };
  }

  function stopPolling() { clearInterval(state.timer); state.timer = null; }

  async function startJob(req) {
    state.lastRequest = req;
    hideBanner();
    state.videos = []; state.byId.clear(); state.after = 0; state.uafter = 0;
    state.selectedId = null; state.shown = PAGE; state.channel = ""; state.fails = 0;
    state.running = true;
    el.status.textContent = "Aloitetaan haku…";
    render();
    let res;
    try {
      res = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    } catch (_) {
      return failJob("Palvelimeen ei saatu yhteyttä. Onko sovellus käynnissä?", "");
    }
    if (!res.ok) return failJob(res.data?.error?.message || `Virhe (${res.status}).`, res.data?.error?.detail || "");
    state.jobId = res.data.id;
    state.timer = setInterval(poll, POLL_MS);
    poll();
  }

  function failJob(message, detail) {
    stopPolling();
    state.running = false;
    el.status.textContent = "Haku epäonnistui.";
    showBanner("✖ " + message + (detail && !message.includes(detail) ? `\n\nTekninen tieto: ${detail}` : ""), "error");
    render();
  }

  let polling = false;
  async function poll() {
    if (polling || !state.jobId) return;
    polling = true;
    const jobId = state.jobId;
    try {
      const res = await api(`/api/jobs/${jobId}?after=${state.after}&uafter=${state.uafter}`);
      if (jobId !== state.jobId) return;
      if (!res.ok) throw new Error(res.data?.error?.message || String(res.status));
      state.fails = 0;
      applySnapshot(res.data);
    } catch (e) {
      if (++state.fails >= MAX_POLL_FAILS) {
        failJob("Yhteys palvelimeen katkesi, haku on osittainen: " + state.videos.length + " videota.", String(e.message || e));
      }
    } finally { polling = false; }
  }

  function applySnapshot(d) {
    for (const v of d.videos) { if (!state.byId.has(v.id)) { state.byId.set(v.id, v); state.videos.push(v); } }
    state.after += d.videos.length;
    for (const u of d.updates) {
      const cur = state.byId.get(u.id);
      if (cur) Object.assign(cur, u);
    }
    state.uafter += d.updates.length;
    el.status.textContent = d.status;
    if (d.state === "running") { render(); return; }
    stopPolling();
    state.running = false;
    if (d.state === "failed") { failJob(d.error.message, d.error.detail); return; }
    finishJob(d.result);
    render();
  }

  function finishJob(r) {
    state.channel = r.channel || "";
    const n = state.videos.length, name = r.channel ? ` kanavalta ${r.channel}` : "";
    let text = r.complete ? `Valmis: ${n} videota${name}.`
      : `Haku päättyi, mutta tulokset eivät ole täydelliset: ${n} videota${name}.`;
    if (r.notes.length) text += "  " + r.notes.join(" ");
    if (!linksOnly() && n && !state.videos.some((v) => v.date)) {
      text += "  Julkaisupäivät eivät sisältyneet listaukseen – valitse ”Hae tarkat julkaisupäivät”.";
    }
    el.status.textContent = text;
    if (r.warnings.length) showBanner("⚠ Tulokset ovat osittaiset.\n• " + r.warnings.join("\n• "), "warn");
  }

  async function cancelJob() {
    if (!state.jobId || !state.running) return;
    el.cancel.disabled = true;
    el.status.textContent = "Keskeytetään…";
    try { await api(`/api/jobs/${state.jobId}/cancel`, { method: "POST" }); } catch (_) { /* poll huomaa */ }
  }

  // ---------- toiminnot ----------
  async function copyLinks() {
    if (!state.visible.length) return;
    const text = state.visible.map((v) => v.url).join("\n");
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly", "");
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.append(ta); ta.select();
      try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
      ta.remove();
    }
    el.status.textContent = ok ? `Kopioitu leikepöydälle: ${state.visible.length} linkkiä.`
      : "Kopiointi epäonnistui (selain esti leikepöydän käytön). Käytä Vie TXT -painiketta.";
  }

  async function exportFile(fmt) {
    if (!state.visible.length) return;
    let res;
    try {
      res = await fetch(`/api/export/${fmt}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videos: state.visible, links_only: linksOnly(), name: state.channel }),
      });
    } catch (_) { showBanner("✖ Vienti epäonnistui: palvelimeen ei saatu yhteyttä.", "error"); return; }
    if (!res.ok) { showBanner("✖ Vienti epäonnistui (" + res.status + ").", "error"); return; }
    const blob = await res.blob();
    const base = (state.channel || "youtube_videot").replace(/[^\p{L}\p{N}_-]+/gu, "_").replace(/^_+|_+$/g, "") || "youtube_videot";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `${base}.${fmt}`;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    el.status.textContent = `Viety ${state.visible.length} riviä (${fmt.toUpperCase()}). Tiedosto tallentuu selaimesi latauskansioon.`;
  }

  function openSelected() {
    const v = state.byId.get(state.selectedId);
    if (!v) return;
    if (!window.open(v.url, "_blank", "noopener,noreferrer")) {
      el.status.textContent = "Selain esti ikkunan avaamisen. Linkki: " + v.url;
    }
  }

  // ---------- tapahtumat ----------
  el.form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.running || el.collect.disabled) return;
    const req = currentRequest();
    if (!req.url) { showBanner("✖ Syötä YouTube-kanavan osoite.", "error"); return; }
    startJob(req);
  });
  el.cancel.addEventListener("click", cancelJob);
  el.retry.addEventListener("click", () => { if (!state.running && state.lastRequest) startJob(state.lastRequest); });
  for (const x of [el.kVideo, el.kShort, el.kLive, el.mLinks, el.mDetails]) x.addEventListener("change", updateControls);
  for (const x of [el.filter, el.kindFilter, el.sort]) x.addEventListener("input", () => { state.shown = PAGE; render(); });
  el.more.addEventListener("click", () => { state.shown += PAGE; render(); });
  el.rows.addEventListener("click", (e) => {
    const tr = e.target.closest("tr"); if (tr) selectRow(tr.dataset.id);
  });
  el.rows.addEventListener("dblclick", (e) => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr"); if (tr) { selectRow(tr.dataset.id); openSelected(); }
  });
  el.rows.addEventListener("keydown", (e) => {
    const tr = e.target.closest("tr");
    if (tr && (e.key === "Enter" || e.key === " ") && e.target === tr) { e.preventDefault(); selectRow(tr.dataset.id); }
  });
  el.copy.addEventListener("click", copyLinks);
  el.txt.addEventListener("click", () => exportFile("txt"));
  el.csv.addEventListener("click", () => exportFile("csv"));
  el.open.addEventListener("click", openSelected);

  render();
})();
