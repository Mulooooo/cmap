"use strict";

const PALETTE = [
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf",
  "#bcbd22", "#7f7f7f", "#393b79", "#e6550d", "#31a354", "#756bb1", "#843c39", "#d6616b",
  "#637939", "#8ca252", "#3182bd", "#fd8d3c",
];
const IDLE = "#4a6fa5";
const BASEMAPS = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};
const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const $ = (id) => document.getElementById(id);
const color = (i) => PALETTE[i % PALETTE.length];

const state = {
  config: null,
  inst: null,      // instance placée sur la carte (réponse de l'API)
  routes: null,    // tournées affichées (indices de clients, sans le dépôt)
  solution: null,  // résultat final du solveur
  live: [],        // [temps, coût] reçus pendant le calcul
  es: null,        // EventSource en cours
};

// ------------------------------------------------------------------ utilitaires
async function api(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* corps non JSON */ }
    throw new Error(msg);
  }
  return res.json();
}

let toastTimer;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 7000);
}

function stat(label, value) {
  const d = document.createElement("div");
  d.className = "stat";
  const b = document.createElement("b");
  b.textContent = value;
  const s = document.createElement("span");
  s.textContent = label;
  d.append(b, s);
  return d;
}

// ------------------------------------------------------------------------ carte
const prefersDark = matchMedia("(prefers-color-scheme: dark)").matches;
$("basemap").value = prefersDark ? "dark" : "light";

const map = new maplibregl.Map({
  container: "map",
  style: BASEMAPS[$("basemap").value],
  center: [2.4, 46.6],
  zoom: 4.8,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

const depotEl = Object.assign(document.createElement("div"), { className: "depot-pin", textContent: "Dépôt" });
const depotMarker = new maplibregl.Marker({ element: depotEl, anchor: "bottom" });
const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });

const EMPTY = { type: "FeatureCollection", features: [] };

function ensureLayers() {
  if (map.getSource("clients")) return;
  map.addSource("clients", { type: "geojson", data: EMPTY });
  map.addSource("routes", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "routes-casing", type: "line", source: "routes",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#ffffff", "line-width": 6.5, "line-opacity": 0.75 } });
  map.addLayer({ id: "routes", type: "line", source: "routes",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 3.5 } });
  map.addLayer({ id: "clients", type: "circle", source: "clients",
    paint: { "circle-radius": ["get", "r"], "circle-color": ["get", "color"],
             "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
}

// écouteurs liés à une couche : à poser une seule fois (ils survivent au rechargement du style)
map.on("mousemove", "clients", (e) => {
  map.getCanvas().style.cursor = "pointer";
  const p = e.features[0].properties;
  const rows = [`<b>Client ${p.id}</b>`, `demande ${p.demand}`];
  if (p.route >= 0) rows.push(`camion ${p.route + 1}, étape ${p.step}`);
  popup.setLngLat(e.features[0].geometry.coordinates).setHTML(rows.join("<br>")).addTo(map);
});
map.on("mouseleave", "clients", () => { map.getCanvas().style.cursor = ""; popup.remove(); });

function render() {
  const inst = state.inst;
  if (!inst || !map.getSource("clients")) return;
  const routes = state.routes || [];
  const owner = new Map();
  routes.forEach((r, ri) => r.forEach((c, k) => owner.set(c, [ri, k + 1])));

  const q = inst.demand.slice(1);
  const qmin = Math.min(...q), span = (Math.max(...q) - qmin) || 1;
  const pt = (i) => [inst.lon[i], inst.lat[i]];

  const clients = [];
  for (let i = 1; i < inst.n; i++) {
    const [ri, step] = owner.get(i) || [-1, 0];
    clients.push({ type: "Feature", geometry: { type: "Point", coordinates: pt(i) },
      properties: { id: i, demand: inst.demand[i], route: ri, step,
        color: ri >= 0 ? color(ri) : IDLE, r: 5 + 7 * (inst.demand[i] - qmin) / span } });
  }
  const lines = routes.map((r, ri) => ({ type: "Feature",
    geometry: { type: "LineString", coordinates: [0, ...r, 0].map(pt) },
    properties: { route: ri, color: color(ri) } }));

  map.getSource("clients").setData({ type: "FeatureCollection", features: clients });
  map.getSource("routes").setData({ type: "FeatureCollection", features: lines });
  depotMarker.setLngLat(pt(0)).addTo(map);
}

function fit() {
  const inst = state.inst;
  if (!inst) return;
  const b = new maplibregl.LngLatBounds();
  inst.lon.forEach((x, i) => b.extend([x, inst.lat[i]]));
  map.fitBounds(b, { padding: 70, duration: 500, maxZoom: 14 });
}

function highlight(route) {  // route = indice du camion, ou null pour tout remettre
  if (!map.getLayer("routes")) return;  // fond de carte en cours de changement : couches absentes
  const on = route !== null;
  map.setPaintProperty("routes", "line-opacity",
    on ? ["case", ["==", ["get", "route"], route], 1, 0.12] : 1);
  map.setPaintProperty("routes-casing", "line-opacity",
    on ? ["case", ["==", ["get", "route"], route], 0.75, 0.05] : 0.75);
  map.setPaintProperty("clients", "circle-opacity",
    on ? ["case", ["==", ["get", "route"], route], 1, 0.25] : 1);
  map.setPaintProperty("clients", "circle-stroke-opacity",
    on ? ["case", ["==", ["get", "route"], route], 1, 0.25] : 1);
}

map.on("load", () => { ensureLayers(); render(); });
map.on("style.load", () => { ensureLayers(); render(); });  // après changement de fond de carte

// -------------------------------------------------------------- affichage texte
function showInstance() {
  const inst = state.inst;
  $("title").textContent = `${inst.name} · ${inst.n - 1} clients`;
  const s = $("stats");
  s.replaceChildren(
    stat("Capacité", inst.capacity),
    stat("Demande totale", inst.total_demand),
    stat("Camions (min.)", inst.min_vehicles),
    stat("Meilleure connue", inst.bks ? nf.format(inst.bks) : "n/a"),
  );
  $("note").hidden = false;
  $("scale").textContent = `Échelle : 1 unité de distance = ${nf.format(inst.km_per_unit)} km.`;
}

function showResults(sol) {
  const inst = state.inst;
  $("results").hidden = false;
  const v = $("verdict");
  v.className = "verdict " + (sol.valid ? "ok" : "bad");
  v.textContent = sol.valid ? `Solution valide (${sol.solver})`
                            : "Solution invalide : " + sol.errors.join(" ; ");

  const km = Math.round(sol.cost * inst.km_per_unit);
  const cards = [
    stat("Coût total", nf.format(sol.cost)),
    stat("≈ km", nf.format(km)),
    stat("Camions utilisés", sol.routes.length),
  ];
  if (sol.gap !== null) cards.push(stat("Gap vs meilleure connue", nf.format(sol.gap) + " %"));
  cards.push(stat("Temps de calcul", nf.format(sol.elapsed) + " s"));
  $("solStats").replaceChildren(...cards);

  const tbody = $("routesTable").querySelector("tbody");
  tbody.replaceChildren(...sol.routes.map((r, i) => {
    const pr = sol.per_route[i];
    const tr = document.createElement("tr");
    const cell = (cls) => { const td = document.createElement("td"); if (cls) td.className = cls; return td; };
    const c1 = cell(); const dot = document.createElement("span");
    dot.className = "dot"; dot.style.background = color(i);
    c1.append(dot, String(i + 1));
    const c2 = cell("path"); c2.textContent = ["D", ...r, "D"].join(" → ");
    const c3 = cell("num"); c3.textContent = pr.n;
    const c4 = cell(); const load = document.createElement("div"); load.className = "load";
    const bar = document.createElement("i"); const fill = document.createElement("em");
    fill.style.width = Math.min(100, 100 * pr.load / inst.capacity) + "%"; bar.append(fill);
    const txt = document.createElement("span"); txt.textContent = `${pr.load}/${inst.capacity}`;
    load.append(bar, txt); c4.append(load);
    const c5 = cell("num"); c5.textContent = nf.format(pr.dist);
    const c6 = cell("num"); c6.textContent = nf.format(Math.round(pr.dist * inst.km_per_unit));
    tr.append(c1, c2, c3, c4, c5, c6);
    tr.addEventListener("mouseenter", () => highlight(i));
    tr.addEventListener("mouseleave", () => highlight(null));
    return tr;
  }));
  drawChart(sol.history.map((h) => [h[0], h[2]]), inst.bks);
}

// ------------------------------------------------- courbe de convergence (SVG)
function drawChart(points, bks) {
  const box = $("chart");
  if (points.length < 2) { box.replaceChildren(); return; }
  const W = 760, H = 260, L = 56, R = 16, T = 14, B = 36;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const xmax = Math.max(...xs) || 1;
  let ymin = Math.min(...ys, bks ?? Infinity), ymax = Math.max(...ys);
  const pad = (ymax - ymin) * 0.08 || 1;
  ymin -= pad; ymax += pad;
  const X = (x) => L + (x / xmax) * (W - L - R);
  const Y = (y) => T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B);

  let d = `M${X(points[0][0])},${Y(points[0][1])}`;
  for (let i = 1; i < points.length; i++) d += ` H${X(points[i][0])} V${Y(points[i][1])}`;  // escalier

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const add = (tag, attrs, text) => {
    const el = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    svg.append(el);
  };
  for (let i = 0; i <= 4; i++) {
    const y = ymin + (i / 4) * (ymax - ymin), x = (i / 4) * xmax;
    add("line", { x1: L, x2: W - R, y1: Y(y), y2: Y(y), stroke: "currentColor", "stroke-opacity": .12 });
    add("text", { x: L - 8, y: Y(y) + 4, "text-anchor": "end" }, nf.format(Math.round(y)));
    add("text", { x: X(x), y: H - 14, "text-anchor": "middle" }, nf.format(Math.round(x * 10) / 10) + " s");
  }
  if (bks) {
    add("line", { x1: L, x2: W - R, y1: Y(bks), y2: Y(bks), stroke: "#2ca02c", "stroke-dasharray": "5 4" });
    add("text", { x: W - R, y: Y(bks) - 5, "text-anchor": "end", fill: "#2ca02c" }, `Meilleure connue : ${nf.format(bks)}`);
  }
  add("path", { d, fill: "none", stroke: "#2563eb", "stroke-width": 2 });
  box.replaceChildren(svg);
}

// ------------------------------------------------------------ instance & carte
async function setInstance(promise) {
  try {
    state.inst = await promise;
  } catch (e) { toast(e.message); return; }
  stopSolve();
  state.routes = null; state.solution = null; state.live = [];
  $("results").hidden = true;
  $("status").hidden = true;
  $("run").disabled = false;
  showInstance();
  render();
  fit();
}

const placement = () => new URLSearchParams({ zone: $("zone").value, span: $("span").value });

async function loadLibrary(name) {  // la zone et l'étendue déjà choisies sont conservées
  await setInstance(api(`/api/instances/library/${encodeURIComponent(name)}?${placement()}`,
    { method: "POST" }));
}

async function uploadFile(file) {
  if (!file) return;
  const q = placement();
  q.set("filename", file.name);
  await setInstance(api(`/api/instances?${q}`, { method: "POST", body: file }));
}

let placeTimer;
function replace() {  // nouvelle zone / étendue : on replace les mêmes points ailleurs
  clearTimeout(placeTimer);
  placeTimer = setTimeout(async () => {
    if (!state.inst) return;
    try {
      const q = new URLSearchParams({ zone: $("zone").value, span: $("span").value });
      state.inst = await api(`/api/instances/${state.inst.id}?${q}`);
    } catch (e) { toast(e.message); return; }
    $("scale").textContent = `Échelle : 1 unité de distance = ${nf.format(state.inst.km_per_unit)} km.`;
    render();
    fit();
    if (state.solution) showResults(state.solution);  // les km changent avec l'échelle
  }, 150);
}

// ----------------------------------------------------------------------- calcul
function setRunning(on) {
  const b = $("run");
  b.textContent = on ? "■ Arrêter" : "▶ Calculer";
  b.classList.toggle("stop", on);
}

function stopSolve() {
  if (state.es) { state.es.close(); state.es = null; }
  setRunning(false);
}

function startSolve() {
  if (!state.inst) return;
  stopSolve();
  setRunning(true);
  state.live = [];
  state.solution = null;
  $("results").hidden = true;
  const st = $("status");
  st.hidden = false;
  st.textContent = "Démarrage du calcul…";

  const q = new URLSearchParams({ instance: state.inst.id, solver: $("solver").value,
    time_limit: $("limit").value, seed: $("seed").value || "0" });
  const es = new EventSource(`/api/solve?${q}`);
  state.es = es;

  es.addEventListener("progress", (ev) => {
    const d = JSON.parse(ev.data);
    state.routes = d.routes;
    state.live.push([d.elapsed, d.cost]);
    st.textContent = `Calcul en cours… ${nf.format(d.elapsed)} s · meilleur coût ${nf.format(d.cost)}`;
    render();
  });
  es.addEventListener("done", (ev) => {
    const sol = JSON.parse(ev.data);
    state.solution = sol;
    state.routes = sol.routes;
    stopSolve();
    st.hidden = true;
    render();
    showResults(sol);
  });
  es.addEventListener("error", (ev) => {
    if (ev.data) {  // erreur envoyée par le serveur (solveur planté)
      toast("Erreur du solveur : " + JSON.parse(ev.data).message);
    } else if (state.es === es) {  // coupure réseau
      toast("Connexion au serveur perdue.");
    }
    stopSolve();
    st.hidden = true;
  });
}

// -------------------------------------------------------------------- démarrage
function bindOutput(inputId, outId, suffix) {
  const input = $(inputId), out = $(outId);
  const sync = () => { out.textContent = `${input.value} ${suffix}`; };
  input.addEventListener("input", sync);
  sync();
}

async function init() {
  state.config = await api("/api/config");
  const fill = (sel, items) => sel.replaceChildren(...items.map((t) => new Option(t, t)));
  fill($("library"), state.config.library);
  fill($("zone"), Object.keys(state.config.zones));
  fill($("solver"), state.config.solvers);
  $("span").value = state.config.zones[$("zone").value].span;
  bindOutput("span", "spanOut", "km");
  bindOutput("limit", "limitOut", "s");

  $("library").addEventListener("change", () => loadLibrary($("library").value));
  $("zone").addEventListener("change", () => {
    $("span").value = state.config.zones[$("zone").value].span;
    $("span").dispatchEvent(new Event("input"));
    replace();
  });
  $("span").addEventListener("input", replace);
  // diff:false = rechargement complet du style, sinon MapLibre retire nos couches sans relancer "style.load"
  $("basemap").addEventListener("change", () =>
    map.setStyle(BASEMAPS[$("basemap").value], { diff: false }));
  $("run").addEventListener("click", () => (state.es ? stopSolve() : startSolve()));

  const drop = $("drop"), file = $("file");
  drop.addEventListener("click", () => file.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") file.click(); });
  file.addEventListener("change", () => { uploadFile(file.files[0]); file.value = ""; });
  for (const t of ["dragenter", "dragover"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); });
  for (const t of ["dragleave", "drop"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); });
  drop.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));
  // un .vrp lâché n'importe où sur la page ne doit pas être ouvert par le navigateur
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => { e.preventDefault(); uploadFile(e.dataTransfer.files[0]); });

  if (state.config.library.length) await loadLibrary(state.config.library[0]);
}

init().catch((e) => toast("Impossible de joindre le serveur : " + e.message));
