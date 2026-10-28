"use strict";
// Renders recorded MCP runs from docs/demo/*.json. Columns are only a display choice; all values come from the recordings.
(() => {
const COLS = {
  "water-use-near-deland": ["distance_miles", "stn_alias_nm", "stn_tp", "stn_stts", "prmt_proj_nm", "prmt_stts"],
  "erp-lake-eola": ["id", "site_nm", "seq_type", "rule_type_desc", "prmt_stts", "recv_dt"],
  "stations-lake-george": ["distance_miles", "stn_name", "station_category", "station_status", "pnt_loc_dsc", "cnty_nm"],
  "trails-in-management-area": ["conservation_area", "trail_blaze", "hiking", "bicycling", "horseback", "miles", "trail_conditions"],
  "erp-by-county": ["value", "count"]
};
const COLOR = ["#0b7285", "#e8590c"];
let done = false;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const val = (f, k) => {
  if (k === "distance_miles") return f.distance_miles;
  if (k === "id") return f.id;
  if (k === "value" || k === "count") return f[k];
  const v = f.properties?.[k];
  if (typeof v === "string" && /^\d{4}-\d\d-\d\dT/.test(v)) return v.slice(0, 10);
  if (typeof v === "number" && !Number.isInteger(v)) return Math.round(v * 100) / 100;
  return v;
};
function table(slug, results, isCount) {
  const cols = isCount ? ["value", "count"] : COLS[slug].filter(k => results.some(f => val(f, k) != null));
  return `<div class="res"><table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
    results.map(f => `<tr>${cols.map(c => `<td>${esc(val(f, c))}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>";
}
function trim(r) {   // shorter raw JSON for display: first 2 results, geometry elided
  const c = JSON.parse(JSON.stringify(r)); const list = Array.isArray(c.results) ? c.results : [c.results];
  list.forEach(f => { if (f && f.geometry) f.geometry = { type: f.geometry.type, coordinates: "…" }; });
  if (Array.isArray(c.results) && c.results.length > 2) c.results = [...c.results.slice(0, 2), `… ${c.results.length - 2} more`];
  return JSON.stringify(c, null, 1);
}
function card(d) {
  const calls = d.calls.map((c, i) => {
    const r = c.result, list = Array.isArray(r.results) ? r.results : (r.results ? [r.results] : []);
    return `<div class="call"><b>${esc(c.tool)}</b>(${esc(JSON.stringify(c.arguments))})</div>
      <div style="font-size:12px;color:var(--mute)">→ ${list.length} result${list.length === 1 ? "" : "s"}${r.count === 25 || r.count === 50 ? " (limit reached)" : ""}</div>
      ${table(d.slug, list, c.tool === "count_by")}
      <details><summary>Raw JSON (trimmed)</summary><pre>${esc(trim(r))}</pre></details>`;
  }).join("");
  return `<article class="demo" id="demo-${d.slug}"><div class="q">${esc(d.question)}
    <small>Recorded ${esc(d.recorded_at.slice(0, 10))} · server ${esc(d.server)} · <a href="demo/${d.slug}.json">full JSON</a></small></div>
    <div class="grid"><div class="calls">${calls}</div><div class="mini" id="mini-${d.slug}" role="img" aria-label="Map of the returned features"></div></div></article>`;
}
function geojson(d) {
  const feats = [];
  d.calls.forEach((c, i) => {
    if (c.tool === "count_by") return;
    const list = Array.isArray(c.result.results) ? c.result.results : [c.result.results];
    list.forEach(f => f && feats.push({ type: "Feature", properties: { step: i, id: f.id },
      geometry: f.geometry || { type: "Point", coordinates: [f.centroid.lon, f.centroid.lat] } }));
    const a = c.arguments;
    if (a.lat != null) feats.push({ type: "Feature", properties: { step: -1 }, geometry: { type: "Point", coordinates: [a.lon, a.lat] } });
    if (Array.isArray(a.bbox)) { const [x1, y1, x2, y2] = a.bbox;
      feats.push({ type: "Feature", properties: { step: -2 }, geometry: { type: "Polygon", coordinates: [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]] } }); }
  });
  return { type: "FeatureCollection", features: feats };
}
function countsMap(el, d) {   // count_by has no geometry: show a bar list instead of a map
  const r = d.calls[0].result.results, max = Math.max(...r.map(x => x.count));
  el.style.padding = "14px"; el.removeAttribute("role");
  el.innerHTML = r.map(x => `<div style="display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px"><span style="width:80px">${esc(x.value)}</span>
    <span style="flex:1;background:var(--bg);border-radius:4px"><span style="display:block;height:14px;border-radius:4px;background:#e8590c;width:${(100 * x.count / max).toFixed(1)}%"></span></span>
    <span style="width:52px;text-align:right">${x.count.toLocaleString("en-US")}</span></div>`).join("");
}
function mini(d) {
  const el = document.getElementById("mini-" + d.slug);
  if (d.calls.every(c => c.tool === "count_by")) return countsMap(el, d);
  const gj = geojson(d); let b = [180, 90, -180, -90];
  const walk = c => typeof c[0] === "number" ? (b = [Math.min(b[0], c[0]), Math.min(b[1], c[1]), Math.max(b[2], c[0]), Math.max(b[3], c[1])]) : c.forEach(walk);
  gj.features.forEach(f => walk(f.geometry.coordinates));
  const dark = document.documentElement.classList.contains("dark");
  const m = new maplibregl.Map({ container: el, attributionControl: { compact: true }, interactive: true, cooperativeGestures: true,
    style: { version: 8, sources: { base: { type: "raster", tileSize: 256, maxzoom: 16, attribution: "Esri, HERE, Garmin, © OpenStreetMap",
      tiles: [`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${dark ? "Dark" : "Light"}_Gray_Base/MapServer/tile/{z}/{y}/{x}`] } },
      layers: [{ id: "base", type: "raster", source: "base" }] }, bounds: [[b[0], b[1]], [b[2], b[3]]], fitBoundsOptions: { padding: 30, maxZoom: 15 } });
  m.on("load", () => {
    m.addSource("r", { type: "geojson", data: gj });
    const col = ["case", ["==", ["get", "step"], 0], COLOR[0], COLOR[1]];
    m.addLayer({ id: "bbox", type: "line", source: "r", filter: ["==", ["get", "step"], -2], paint: { "line-color": "#868e96", "line-dasharray": [2, 2] } });
    m.addLayer({ id: "fill", type: "fill", source: "r", filter: ["all", ["==", ["geometry-type"], "Polygon"], [">=", ["get", "step"], 0]], paint: { "fill-color": col, "fill-opacity": 0.25 } });
    m.addLayer({ id: "line", type: "line", source: "r", filter: [">=", ["get", "step"], 0], paint: { "line-color": col, "line-width": 2.5 } });
    m.addLayer({ id: "pt", type: "circle", source: "r", filter: ["all", ["==", ["geometry-type"], "Point"], [">=", ["get", "step"], 0]],
      paint: { "circle-color": col, "circle-radius": 5, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });
    m.addLayer({ id: "q", type: "circle", source: "r", filter: ["==", ["get", "step"], -1],
      paint: { "circle-color": "#fff", "circle-radius": 7, "circle-stroke-color": "#c92a2a", "circle-stroke-width": 3 } });
  });
}
window.renderDemos = async () => {
  if (done) return; done = true;
  const index = await fetch("demo/index.json").then(r => r.json());
  const all = await Promise.all(index.map(x => fetch(`demo/${x.slug}.json`).then(r => r.json())));
  document.getElementById("demos").innerHTML = all.map(card).join("");
  all.forEach(mini);
};
if (location.hash.startsWith("#demo")) window.renderDemos();
})();
