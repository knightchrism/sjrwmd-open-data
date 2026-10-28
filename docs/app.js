"use strict";
const META = {
  erp:                   ["Environmental Resource Permits", "Permits", "#e8590c", "Permit areas with permit numbers, dates and status: the core regulatory layer."],
  cup_boundary:          ["Consumptive Use Permit boundaries", "Permits", "#f59f00", "Water-use permit project boundaries; join to CUP stations by permit number."],
  conservation_easement: ["Regulatory conservation easements", "Permits", "#2f9e44", "Recorded permit easements, key for parcel due diligence."],
  cup_station:           ["CUP wells & withdrawal points", "Permits", "#d6336c", "Permitted wells and withdrawal points, with permit numbers and status."],
  well_completion:       ["Well completion permits", "Permits", "#ae3ec9", "District-issued well construction permits, with dates."],
  reuse_line:            ["Reclaimed-water lines", "Permits", "#7048e8", "Reclaimed-water lines reported to the district."],
  edr_station:           ["Monitoring stations (EDR)", "Monitoring", "#1c7ed6", "Hydrologic and water-quality monitoring stations."],
  st2025_surface_water:  ["2025 Status & Trends: surface water", "Monitoring", "#15aabf", "2025 Status & Trends surface-water stations."],
  st2025_groundwater:    ["2025 Status & Trends: groundwater", "Monitoring", "#0b7285", "2025 Status & Trends groundwater stations."],
  ufa_potentiometric_2010:["Upper Floridan potentiometric surface (2010)", "Monitoring", "#4263eb", "Latest (Sep 2010) Upper Floridan aquifer potentiometric contours."],
  management_area:       ["District management areas", "District lands", "#37b24d", "District-managed conservation lands, with manager and acres."],
  management_area_trail: ["Management-area trails", "District lands", "#a9e34b", "Public recreation trails on district lands."],
  management_area_road:  ["Management-area roads", "District lands", "#868e96", "Roads on district lands."],
  land_use_2020:         ["Land cover / land use 2020", "Land & water", "#fab005", "Latest district land use/land cover (FLUCCS) vintage."],
  stream_flowpath:       ["Streams (1:24K flowpaths)", "Land & water", "#339af0", "District 1:24K stream network, more detailed than USGS 100K."]
};
const GROUPS = ["Permits", "Monitoring", "District lands", "Land & water"];
const DEFAULT_ON = ["management_area", "erp"];
const ESRI = n => [`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${n}/MapServer/tile/{z}/{y}/{x}`];
const BASE = { light: ESRI("World_Light_Gray_Base"), dark: ESRI("World_Dark_Gray_Base") };
const ATTR = 'Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors | Data: <a href="https://www.sjrwmd.com">SJRWMD</a> (unofficial mirror)';
const $ = s => document.querySelector(s);
const fmt = n => n == null ? "–" : Number(n).toLocaleString("en-US");
const day = s => s ? new Date(s).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "–";
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ICON = (g, c) => g === "Point" ? `<svg class="ico" viewBox="0 0 22 22" aria-hidden="true"><circle cx="7" cy="8" r="3.2" fill="${c}"/><circle cx="15" cy="14" r="3.2" fill="${c}"/><circle cx="15" cy="6" r="2.2" fill="${c}" opacity=".6"/></svg>`
  : g === "Polyline" ? `<svg class="ico" viewBox="0 0 22 22" aria-hidden="true"><path d="M2 17 L8 9 L13 13 L20 4" stroke="${c}" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`
  : `<svg class="ico" viewBox="0 0 22 22" aria-hidden="true"><path d="M3 6 L12 3 L19 8 L17 18 L6 19 Z" fill="${c}" fill-opacity=".35" stroke="${c}" stroke-width="2"/></svg>`;

// ---------- theme ----------
let dark = localStorage.getItem("theme") ? localStorage.getItem("theme") === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
document.documentElement.classList.toggle("dark", dark);

// ---------- map ----------
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);
const map = new maplibregl.Map({
  container: "map", center: [-81.35, 29.0], zoom: 7, hash: "view", maxZoom: 17, attributionControl: false,
  style: { version: 8, sources: { base: { type: "raster", tiles: BASE[dark ? "dark" : "light"], tileSize: 256, attribution: ATTR, maxzoom: 16 } },
    layers: [{ id: "base", type: "raster", source: "base" }] }
});
map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
map.addControl(new maplibregl.FullscreenControl(), "top-right");

$("#theme").addEventListener("click", () => {
  dark = !dark; localStorage.setItem("theme", dark ? "dark" : "light");
  document.documentElement.classList.toggle("dark", dark);
  map.getSource("base").setTiles(BASE[dark ? "dark" : "light"]);
});

// ---------- tabs ----------
function showTab() {
  const t = (location.hash.match(/^#(downloads|about)/) || [, "map"])[1];
  document.querySelectorAll(".view").forEach(v => v.hidden = v.id !== "view-" + t);
  document.querySelectorAll(".tabs a[data-tab]").forEach(a => { a.classList.toggle("on", a.dataset.tab === t); a.setAttribute("aria-selected", a.dataset.tab === t); });
  if (t === "map") map.resize();
}
window.addEventListener("hashchange", showTab); showTab();
document.querySelectorAll('.tabs a[data-tab="map"]').forEach(a => a.addEventListener("click", e => { e.preventDefault(); history.pushState(null, "", location.pathname); showTab(); }));
$("#collapse").addEventListener("click", e => { const s = $("#side"); s.classList.toggle("closed"); e.target.setAttribute("aria-expanded", !s.classList.contains("closed")); });

// ---------- data ----------
let catalog; const on = new Set();
fetch("data/catalog.json").then(r => r.json()).then(c => {
  catalog = c;
  c.layers.forEach(l => { const m = META[l.alias] || [l.title, "Other", "#868e96", ""]; Object.assign(l, { name: m[0], group: m[1], color: m[2], why: m[3] }); });
  const s = c.summary;
  $("#stats").innerHTML = [[fmt(s.features), "features"], [`${s.counts_matching}/${s.layers}`, "counts match server"], [day(s.last_harvested), "last harvested"]]
    .map(([v, k]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
  renderLayers(); renderDownloads();
  const go = () => DEFAULT_ON.forEach(a => { const cb = document.querySelector(`input[data-alias="${a}"]`); if (cb) { cb.checked = true; toggle(a, true); } });
  map.loaded() ? go() : map.on("load", go);
});

function chips(l) {
  return Object.entries(l.downloads || {}).map(([k, u]) => `<a class="dl" href="${u}" download>${k.replace(" (WKT)", "")}</a>`).join("") +
    `<a href="${l.source_url}" target="_blank" rel="noopener">ArcGIS REST</a>` + (l.hub_item ? `<a href="${l.hub_item}" target="_blank" rel="noopener">Hub</a>` : "");
}

function renderLayers() {
  const el = $("#layers");
  el.innerHTML = GROUPS.map(g => {
    const ls = catalog.layers.filter(l => l.group === g); if (!ls.length) return "";
    return `<div class="grp">${g}</div>` + ls.map(l => `
      <div class="lyr" style="--c:${l.color}" data-q="${esc((l.name + " " + l.alias + " " + l.title + " " + g).toLowerCase())}">
        <label><input type="checkbox" data-alias="${l.alias}" aria-label="Show ${esc(l.name)}">${ICON(l.geometry, l.color)}<span>${esc(l.name)}</span></label>
        <div class="meta">${fmt(l.features)} features · edited ${day(l.last_edit)} · <span class="${l.count_match ? "ok" : "bad"}" title="rows loaded vs. server count">${l.count_match ? "✓ complete" : "✗ count mismatch"}</span></div>
        <div class="why">${esc(l.why)}</div>
        <div class="chips">${chips(l)}</div>
      </div>`).join("");
  }).join("");
  el.querySelectorAll("input").forEach(cb => cb.addEventListener("change", e => toggle(e.target.dataset.alias, e.target.checked)));
  $("#filter").addEventListener("input", e => { const q = e.target.value.trim().toLowerCase();
    el.querySelectorAll(".lyr").forEach(d => d.hidden = !d.dataset.q.includes(q)); });
}

function renderDownloads() {
  $("#sums").href = (catalog.layers[0].downloads.GeoPackage || "").replace(/[^/]*$/, "SHA256SUMS");
  $("#dltable tbody").innerHTML = GROUPS.flatMap(g => catalog.layers.filter(l => l.group === g)).map(l => `<tr>
    <td><div style="display:flex;gap:8px;align-items:center">${ICON(l.geometry, l.color)}<div><b>${esc(l.name)}</b><br><small style="color:var(--mute)">${esc(l.why)}</small></div></div></td>
    <td>${l.geometry === "Polyline" ? "Line" : l.geometry}</td><td class="num">${fmt(l.features)}</td><td>${day(l.last_edit)}</td>
    <td><div class="chips">${chips(l)}</div></td></tr>`).join("");
}

function legend() {
  const ls = catalog.layers.filter(l => on.has(l.alias));
  $("#legend").innerHTML = ls.length ? "<h4>Legend</h4>" + ls.map(l => `<div>${ICON(l.geometry, l.color)}${esc(l.name)}</div>`).join("") : "";
}

function toggle(alias, show) {
  const l = catalog.layers.find(x => x.alias === alias), id = l.id;
  const ids = [id + "-fill", id + "-line", id + "-pt"];
  show ? on.add(alias) : on.delete(alias);
  document.querySelector(`input[data-alias="${alias}"]`).closest(".lyr").classList.toggle("on", show); legend();
  if (!show) { ids.forEach(i => map.getLayer(i) && map.setLayoutProperty(i, "visibility", "none")); return; }
  if (map.getSource(id)) { ids.forEach(i => map.getLayer(i) && map.setLayoutProperty(i, "visibility", "visible")); return; }
  map.addSource(id, { type: "vector", url: "pmtiles://" + new URL(l.tiles, location.href).href, attribution: "SJRWMD" });
  const base = { source: id, "source-layer": id };
  if (l.geometry === "Polygon") {
    map.addLayer({ id: id + "-fill", type: "fill", ...base, paint: { "fill-color": l.color, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.22, 14, 0.15] } });
    map.addLayer({ id: id + "-line", type: "line", ...base, paint: { "line-color": l.color, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.4, 14, 1.6] } });
  } else if (l.geometry === "Polyline") {
    map.addLayer({ id: id + "-line", type: "line", ...base, layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": l.color, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.8, 14, 2.6] } });
  } else {
    map.addLayer({ id: id + "-pt", type: "circle", ...base, paint: { "circle-color": l.color, "circle-opacity": 0.9,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 1.8, 10, 3.5, 15, 7], "circle-stroke-color": dark ? "#0d1117" : "#fff", "circle-stroke-width": 0.8 } });
  }
  ids.forEach(i => { if (!map.getLayer(i)) return;
    map.on("click", i, e => popup(e, l));
    map.on("mouseenter", i, () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", i, () => map.getCanvas().style.cursor = ""); });
}

const DATEY = /(_dt|date)$/;
function popup(e, l) {
  const p = e.features[0].properties;
  const rows = Object.entries(p).filter(([k, v]) => !k.startsWith("_") && v !== "" && v != null && !/^shape__/.test(k))
    .map(([k, v]) => {
      let val = esc(v);
      if (DATEY.test(k) && !isNaN(Date.parse(v))) val = day(v);
      else if (/^https?:\/\//.test(v)) val = `<a href="${esc(v)}" target="_blank" rel="noopener">open link ↗</a>`;
      else if (typeof v === "number" && !/id|oid|no$/.test(k)) val = fmt(Math.round(v * 100) / 100);
      return `<tr><td>${esc(k)}</td><td>${val}</td></tr>`; }).join("");
  new maplibregl.Popup({ maxWidth: "380px", focusAfterOpen: false }).setLngLat(e.lngLat)
    .setHTML(`<div class="pop" style="--c:${l.color}"><h3>${esc(l.name)}</h3><div class="body"><table>${rows}</table></div>
      <small>Source: SJRWMD · as of ${day(l.last_edit)} · unofficial mirror</small></div>`).addTo(map);
}
