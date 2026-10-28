#!/usr/bin/env python3
"""Write docs/data/catalog.json (layers, counts, last-edit dates, count match) for the static web map."""
import json, os, re, sys, datetime as dt
import psycopg

TILE_BASE = os.environ.get("TILE_BASE", "tiles/")          # where <table>.pmtiles lives (relative or absolute URL)
DOWNLOAD_BASE = os.environ.get("DOWNLOAD_BASE", "")         # e.g. a release URL; empty = no download links for files
THEMES = [("Permits & regulation", r"permit|erp|cup|wup|consent|mitigation|easement|compliance|well_compl|wetland_det|preapp|reuse|water_use"),
          ("Hydrologic & monitoring", r"station|monitor|gwmn|groundwater|edr|wri|rain|gauge|spring|status_trends|benchmark|bathym|water_quality|sav|seagrass"),
          ("District lands", r"management_area|parcel|district_r|dstrct|trail|campsite|parking|recreat|acquisition|natural_comm|land_acq"),
          ("Land use & cover", r"land_cover|land_use|lulc|wetlands_veg|plant_c|vegetation|soil"),
          ("Hydrography & basins", r"hydro|stream|river|basin|watershed|waterbody|lake|flowpath|huc|mfl|lagoon"),
          ("Boundaries & reference", r"boundar|county|district|survey|plss|section|township|city|road")]

def theme(*names):
    s = " ".join(n.lower() for n in names if n)
    for t, rx in THEMES:
        if re.search(rx, s): return t
    return "Other"

def main(out="docs/data/catalog.json"):
    with psycopg.connect() as c:
        rows = c.execute("""select r.name, r.alias, r.layer_title, r.service, r.layer_id, r.source_url, r.hub_item_id, r.geometry_type,
                                   r.server_count, r.last_edit_date, r.last_harvested_at, r.last_status
                            from meta.layer_registry r where r.alias is not null order by r.service, r.layer_id""").fetchall()
        local = {}
        for (name,) in [r[:1] for r in rows]:
            try: local[name] = c.execute(f'select count(*) from sjrwmd."{name}"').fetchone()[0]
            except Exception: c.rollback(); local[name] = None
    layers = []
    for (name, alias, title, service, lid, url, hub, gtype, cnt, le, fetched, status) in rows:
        g = (gtype or "").replace("esriGeometry", "") or "Table"
        layers.append(dict(id=name, alias=alias, title=title or name, service=service, layer_id=lid, source_url=url,
                           hub_item=f"https://data-floridaswater.opendata.arcgis.com/datasets/{hub}" if hub else None,
                           theme=theme(service, title), geometry=g, features=cnt,
                           last_edit=le.isoformat() if le else None, harvested=fetched.isoformat() if fetched else None,
                           status=status, loaded=local.get(name), count_match=(local.get(name) == cnt),
                           tiles=(TILE_BASE + name + ".pmtiles") if g != "Table" else None,
                           downloads={"GeoPackage": f"{DOWNLOAD_BASE}{alias or name}.gpkg", "GeoParquet": f"{DOWNLOAD_BASE}{alias or name}.parquet", "CSV (WKT)": f"{DOWNLOAD_BASE}{alias or name}.csv.zip"} if DOWNLOAD_BASE else {},
                           arcgis_query=url + "/query?where=1%3D1&outFields=*&f=geojson"))
    summary = dict(generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), layers=len(layers),
                   features=sum(l["features"] or 0 for l in layers),
                   loaded=sum(l["loaded"] or 0 for l in layers),
                   counts_matching=sum(1 for l in layers if l["count_match"]),
                   last_edit=max((l["last_edit"] for l in layers if l["last_edit"]), default=None),
                   last_harvested=max((l["harvested"] for l in layers if l["harvested"]), default=None))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(dict(summary=summary, layers=layers), open(out, "w"), separators=(",", ":"))
    print(json.dumps(summary))

if __name__ == "__main__": main(*sys.argv[1:])
