#!/usr/bin/env python3
"""SJRWMD ArcGIS Online -> PostGIS harvester.

For each layer in the inventory:
  * reads the layer definition and builds a typed table (esriFieldType -> Postgres type);
  * pages by OBJECTID ranges (returnIdsOnly, then where=OID BETWEEN a AND b) in Esri JSON, in the target SRID;
  * assembles Esri polygon rings by orientation (outer = clockwise, holes = counter-clockwise), the way GDAL does.
    The server's f=geojson output emits every ring as its own polygon, which made holes into "nested shells";
  * adds provenance columns and runs a hash-diff upsert plus delete in one transaction;
  * skips the layer when lastEditDate, the server count and the schema are unchanged (use --force to override);
  * logs every attempt to meta.harvest_run.

Usage: python harvest.py [--force] [--only TABLE_OR_ALIAS ...] [--limit N]
Env:   libpq variables (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD); SJRWMD_UA optional
"""
import argparse, csv, datetime as dt, hashlib, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
import psycopg, requests, yaml
from shapely.geometry import LinearRing, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely import wkb as swkb

HERE = os.path.dirname(os.path.abspath(__file__))
UA = os.environ.get("SJRWMD_UA", "sjrwmd-open-data harvester (+https://github.com/knightchrism/sjrwmd-open-data)")
_local = threading.local()
DELAY = 0.3

TYPES = {"esriFieldTypeSmallInteger": "smallint", "esriFieldTypeInteger": "integer", "esriFieldTypeBigInteger": "bigint",
         "esriFieldTypeSingle": "real", "esriFieldTypeDouble": "double precision", "esriFieldTypeString": "text",
         "esriFieldTypeDate": "timestamptz", "esriFieldTypeDateOnly": "date", "esriFieldTypeTimeOnly": "time",
         "esriFieldTypeTimestampOffset": "timestamptz", "esriFieldTypeGUID": "text", "esriFieldTypeGlobalID": "text",
         "esriFieldTypeXML": "text", "esriFieldTypeOID": "bigint"}
GEOMS = {"esriGeometryPoint": "Point", "esriGeometryMultipoint": "MultiPoint",
         "esriGeometryPolyline": "MultiLineString", "esriGeometryPolygon": "MultiPolygon"}
RESERVED = {"_geom_repaired", "geom", "source_oid", "attrs", "_source_url", "_hub_item_id", "_fetched_at", "_source_last_edit", "_hash"}

def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session(); _local.s.headers["User-Agent"] = UA
    return _local.s

def get(url, **params):
    params.setdefault("f", "json")
    for attempt in range(6):
        time.sleep(DELAY)
        try:
            r = session().post(url, data=params, timeout=180)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status(); d = r.json()
            if isinstance(d, dict) and "error" in d: raise RuntimeError(json.dumps(d["error"])[:300])
            return d
        except Exception:
            if attempt == 5: raise
            time.sleep(min(60, 2 ** attempt * 2))

def ident(s, maxlen=63):
    s = re.sub(r"[^a-z0-9_]", "_", s.lower()).strip("_") or "f"
    if s[0].isdigit(): s = "f_" + s
    if len(s) > maxlen: s = s[: maxlen - 9] + "_" + hashlib.md5(s.encode()).hexdigest()[:8]
    return s

def table_name(service, layer_id): return ident(f"{service}_{layer_id}", 58)  # room for _4326 suffix

def ts(ms): return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) if ms is not None else None

def esri_to_shape(g, gtype):
    if not g: return None
    if gtype == "esriGeometryPoint":
        return None if g.get("x") is None or g.get("x") != g.get("x") else Point(g["x"], g["y"])
    if gtype == "esriGeometryMultipoint":
        return MultiPoint(g["points"]) if g.get("points") else None
    if gtype == "esriGeometryPolyline":
        paths = [p for p in g.get("paths", []) if len(p) >= 2]
        return MultiLineString(paths) if paths else None
    if gtype == "esriGeometryPolygon":
        shells, holes = [], []
        for ring in g.get("rings", []):
            pts = [tuple(p[:2]) for p in ring]
            if len(pts) < 4: continue
            lr = LinearRing(pts)
            (holes if lr.is_ccw else shells).append(lr)  # Esri: clockwise = exterior
        if not shells:  # some services return all rings counter-clockwise; treat them as shells
            shells, holes = holes, []
        polys = [[s, []] for s in shells]
        sp = [Polygon(s) for s in shells]
        for h in holes:
            pt = Point(h.coords[0]); best = None
            for i, p in enumerate(sp):
                if p.covers(pt) and (best is None or p.area < sp[best].area): best = i
            if best is None: polys.append([LinearRing(list(h.coords)[::-1]), []])
            else: polys[best][1].append(h)
        return MultiPolygon([Polygon(s, hs) for s, hs in polys]) if polys else None
    return None

def norm(v, ftype):
    if v is None: return None
    if ftype in ("esriFieldTypeDate", "esriFieldTypeTimestampOffset") and isinstance(v, (int, float)):
        try: return ts(v)
        except (OverflowError, OSError, ValueError): return None
    return v

def harvest(cfg, row, force, aliases):
    service, lid = row["service"], int(row["layer_id"])
    url = f"{cfg['base_url']}/{service}/FeatureServer/{lid}"
    name, srid, t0 = table_name(service, lid), cfg["target_srid"], time.time()
    alias = aliases.get(f"{service}/{lid}")
    conn = psycopg.connect(autocommit=False, options="-c client_min_messages=warning")
    try:
        info = get(url)
        gtype = info.get("geometryType")
        oid_field = info.get("objectIdField") or next((f["name"] for f in info["fields"] if f["type"] == "esriFieldTypeOID"), "OBJECTID")
        fields, cols, seen = [], [], set(RESERVED)
        for f in info.get("fields", []):
            if f["type"] in ("esriFieldTypeGeometry", "esriFieldTypeBlob", "esriFieldTypeRaster"): continue
            c = ident(f["name"])
            while c in seen: c += "_"
            seen.add(c); fields.append(f); cols.append((c, TYPES.get(f["type"], "text")))
        schema_sig = hashlib.md5(json.dumps(["v2", cols, gtype, srid, cfg.get("keep_raw_attrs")]).encode()).hexdigest()
        last_edit = ts((info.get("editingInfo") or {}).get("lastEditDate"))
        server_count = get(f"{url}/query", where="1=1", returnCountOnly="true")["count"]
        with conn.cursor() as cur:
            cur.execute("INSERT INTO meta.harvest_run(name, server_count, last_edit_date) VALUES (%s,%s,%s) RETURNING run_id",
                        (name, server_count, last_edit)); run_id = cur.fetchone()[0]
            cur.execute("SELECT last_edit_date, server_count, last_status, schema_sig FROM meta.layer_registry WHERE name=%s", (name,))
            prev = cur.fetchone()
        conn.commit()
        if not force and prev and prev[2] == "ok" and prev[0] == last_edit and prev[1] == server_count and prev[3] == schema_sig:
            with conn.cursor() as cur:
                cur.execute("UPDATE meta.harvest_run SET finished_at=now(), status='skipped', seconds=%s, message='unchanged' WHERE run_id=%s",
                            (round(time.time() - t0, 2), run_id))
            conn.commit(); return dict(name=name, status="skipped", server=server_count, secs=round(time.time() - t0, 1))

        ids = sorted(get(f"{url}/query", where="1=1", returnIdsOnly="true").get("objectIds") or [])
        page = min(cfg.get("page_size", 1000), info.get("maxRecordCount") or 1000)
        now = dt.datetime.now(dt.timezone.utc)
        geom_col = gtype in GEOMS
        coldefs = ",\n".join(f'"{c}" {t}' for c, t in cols)
        with conn.cursor() as cur:
            if prev and prev[3] != schema_sig:
                cur.execute(f"DROP TABLE IF EXISTS sjrwmd.{name} CASCADE")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS sjrwmd.{name} (
                source_oid bigint PRIMARY KEY, {coldefs},
                {"geom geometry(%s, %d)," % (GEOMS[gtype], srid) if geom_col else ""}
                {"attrs jsonb," if cfg.get("keep_raw_attrs") else ""}
                _source_url text NOT NULL, _hub_item_id text, _fetched_at timestamptz NOT NULL,
                _source_last_edit timestamptz, _hash text NOT NULL, _geom_repaired boolean NOT NULL DEFAULT false)""")
            if geom_col:
                cur.execute(f"CREATE INDEX IF NOT EXISTS {ident(name + '_gix')} ON sjrwmd.{name} USING gist (geom)")
            cur.execute(f"""CREATE TEMP TABLE stage (LIKE sjrwmd.{name} INCLUDING DEFAULTS) ON COMMIT DROP""")
            names = ["source_oid"] + [c for c, _ in cols] + (["geom"] if geom_col else []) + \
                    (["attrs"] if cfg.get("keep_raw_attrs") else []) + ["_source_url", "_hub_item_id", "_fetched_at", "_source_last_edit", "_hash"]
            fetched = 0
            with cur.copy(f"COPY stage ({','.join(chr(34)+n+chr(34) for n in names)}) FROM STDIN") as cp:
                for i in range(0, len(ids), page):
                    chunk = ids[i:i + page]
                    d = get(f"{url}/query", where=f"{oid_field} >= {chunk[0]} AND {oid_field} <= {chunk[-1]}",
                            outFields="*", outSR=srid, returnGeometry="true" if geom_col else "false")
                    for feat in d.get("features", []):
                        a = feat.get("attributes") or {}
                        g = esri_to_shape(feat.get("geometry"), gtype) if geom_col else None
                        if g is not None and g.is_empty: g = None
                        h = hashlib.md5(json.dumps([a, feat.get("geometry")], sort_keys=True, default=str).encode()).hexdigest()
                        vals = [a.get(oid_field)] + [norm(a.get(f["name"]), f["type"]) for f in fields]
                        if geom_col: vals.append(None if g is None else swkb.dumps(g, hex=True, srid=srid))
                        if cfg.get("keep_raw_attrs"): vals.append(json.dumps(a))
                        vals += [url, row.get("hub_item_id") or None, now, last_edit, h]
                        cp.write_row(vals); fetched += 1
            if gtype == "esriGeometryPolygon":
                # Esri allows self-touching rings that OGC/GEOS treat as invalid; repair them and flag the row.
                cur.execute("""UPDATE stage SET geom = ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)), _geom_repaired = true
                               WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)""")
            setcols = ", ".join(f'"{n}"=excluded."{n}"' for n in names[1:] + ["_geom_repaired"])
            cur.execute(f"""WITH up AS (
                INSERT INTO sjrwmd.{name} AS t SELECT * FROM stage
                ON CONFLICT (source_oid) DO UPDATE SET {setcols}
                WHERE t._hash IS DISTINCT FROM excluded._hash RETURNING (xmax = 0) AS ins)
                SELECT count(*) FILTER (WHERE ins), count(*) FILTER (WHERE NOT ins) FROM up""")
            ins, upd = cur.fetchone()
            cur.execute(f"DELETE FROM sjrwmd.{name} t WHERE NOT EXISTS (SELECT 1 FROM stage s WHERE s.source_oid = t.source_oid)")
            dele = cur.rowcount
            if geom_col:
                cur.execute(f"""CREATE OR REPLACE VIEW sjrwmd.{name}_4326 AS SELECT {', '.join('t.'+chr(34)+n+chr(34) for n in names if n != 'geom')}, t._geom_repaired,
                                ST_Transform(t.geom, 4326)::geometry({GEOMS[gtype]}, 4326) AS geom FROM sjrwmd.{name} t""")
            if alias:
                cur.execute(f"CREATE OR REPLACE VIEW sjrwmd.{alias} AS SELECT * FROM sjrwmd.{name}")
            cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA sjrwmd TO sjrwmd_reader")
            status = "ok" if fetched == server_count else "count_mismatch"
            cur.execute("""INSERT INTO meta.layer_registry(name, service, layer_id, source_url, hub_item_id, geometry_type, max_record_count,
                             last_edit_date, server_count, last_harvested_at, last_status, schema_sig, alias, layer_title)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s)
                           ON CONFLICT (name) DO UPDATE SET last_edit_date=excluded.last_edit_date, server_count=excluded.server_count,
                             last_harvested_at=now(), last_status=excluded.last_status, geometry_type=excluded.geometry_type,
                             max_record_count=excluded.max_record_count, schema_sig=excluded.schema_sig, alias=excluded.alias,
                             hub_item_id=excluded.hub_item_id, layer_title=excluded.layer_title""",
                        (name, service, lid, url, row.get("hub_item_id") or None, gtype, info.get("maxRecordCount"), last_edit,
                         server_count, status, schema_sig, alias, info.get("name")))
            cur.execute("""UPDATE meta.harvest_run SET finished_at=now(), status=%s, fetched=%s, inserted=%s, updated=%s, deleted=%s,
                           unchanged=%s, seconds=%s WHERE run_id=%s""",
                        (status, fetched, ins, upd, dele, fetched - ins - upd, round(time.time() - t0, 2), run_id))
        conn.commit()
        return dict(name=name, status=status, server=server_count, fetched=fetched, ins=ins, upd=upd, dele=dele,
                    secs=round(time.time() - t0, 1))
    except Exception as e:
        conn.rollback()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO meta.harvest_run(name, finished_at, status, message, seconds) VALUES (%s, now(), 'error', %s, %s)",
                            (name, str(e)[:1000], round(time.time() - t0, 2)))
            conn.commit()
        except Exception: pass
        return dict(name=name, status="error", error=str(e)[:300])
    finally:
        conn.close()

def main():
    global DELAY
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true"); ap.add_argument("--only", nargs="*"); ap.add_argument("--limit", type=int)
    ap.add_argument("--config", default=os.path.join(HERE, "layers.yaml")); a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config)); DELAY = cfg.get("request_delay_s", 0.3)
    aliases = cfg.get("aliases") or {}
    rows = list(csv.DictReader(open(os.path.join(HERE, cfg["inventory"]))))
    if a.only:
        want = set(a.only)
        rows = [r for r in rows if table_name(r["service"], int(r["layer_id"])) in want
                or aliases.get(f"{r['service']}/{r['layer_id']}") in want]
    rows.sort(key=lambda r: -int(r.get("feature_count") or 0))  # biggest first so the long tail overlaps
    if a.limit: rows = rows[: a.limit]
    with ThreadPoolExecutor(cfg.get("workers", 2)) as ex:
        futs = [ex.submit(harvest, cfg, r, a.force, aliases) for r in rows]
        for f in futs:
            print(json.dumps(f.result(), default=str), flush=True)
    sys.exit(0)

if __name__ == "__main__": main()
