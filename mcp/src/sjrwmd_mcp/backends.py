"""Query backends. Every query is a fixed SQL template: layer and field names come only from the whitelist
(validated before use), and every user value is a bound parameter."""
from __future__ import annotations
import json, math, os, pathlib, threading, urllib.request
from datetime import date, datetime
from decimal import Decimal
from .layers import HIDDEN, ID_FIELD, LAYERS, check_layer, clamp_limit, parquet_url

M_PER_MILE = 1609.344

def _jsonable(v):
    if isinstance(v, (datetime, date)): return v.isoformat()
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    return v

def _feature(layer, cols, row, include_geometry):
    rec = dict(zip(cols, row))
    out = {"layer": layer, "id": rec.pop(ID_FIELD, None)}
    lat, lon, geo = rec.pop("__lat", None), rec.pop("__lon", None), rec.pop("__geojson", None)
    dist = rec.pop("__dist_m", None)
    out["centroid"] = {"lat": round(lat, 6), "lon": round(lon, 6)} if lat is not None else None
    if dist is not None: out["distance_miles"] = round(dist / M_PER_MILE, 3)
    out["properties"] = {k: _jsonable(v) for k, v in rec.items() if v is not None and not k.startswith("_")}
    if include_geometry and geo: out["geometry"] = json.loads(geo)
    return out

def _bbox(bbox):
    if isinstance(bbox, str): bbox = [float(x) for x in bbox.split(",")]
    if len(bbox) != 4: raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")
    x1, y1, x2, y2 = map(float, bbox)
    if not (x1 < x2 and y1 < y2): raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat] with min < max")
    if (x2 - x1) * (y2 - y1) > 25: raise ValueError("bbox too large (max 25 square degrees)")
    return x1, y1, x2, y2

def _check_point(lat, lon, radius_miles):
    lat, lon, r = float(lat), float(lon), float(radius_miles)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("lat/lon out of range")
    if not (0 < r <= 50): raise ValueError("radius_miles must be > 0 and <= 50")
    return lat, lon, r


class Backend:
    name = "base"
    def __init__(self):
        self._fields: dict[str, list[tuple[str, str]]] = {}
        self._lock = threading.Lock()

    def fields(self, layer) -> list[tuple[str, str]]:
        check_layer(layer)
        if layer not in self._fields:
            self._fields[layer] = [(c, t) for c, t in self._describe(layer) if c not in HIDDEN and c != ID_FIELD and not c.startswith("_")]
        return self._fields[layer]

    def check_field(self, layer, field) -> str:
        names = [c for c, _ in self.fields(layer)]
        if field not in names:
            raise ValueError(f"unknown field {field!r} for {layer}; fields: {', '.join(names)}")
        return field


class DuckDBBackend(Backend):
    """Default: DuckDB (spatial + httpfs) reading GeoParquet from the GitHub release, optionally cached on disk."""
    name = "duckdb"
    def __init__(self, cache_dir: str | None = None):
        super().__init__()
        import duckdb
        self.cache_dir = pathlib.Path(cache_dir).expanduser() if cache_dir else None
        self.con = duckdb.connect(":memory:")
        for ext in ("spatial", "httpfs"):
            try: self.con.execute(f"LOAD {ext}")
            except Exception:
                self.con.execute(f"INSTALL {ext}"); self.con.execute(f"LOAD {ext}")
        self.con.execute("SET lock_configuration = true")

    def _src(self, layer):
        url = parquet_url(layer)
        if self.cache_dir:
            p = self.cache_dir / f"{layer}.parquet"
            if not p.exists():
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".part")
                urllib.request.urlretrieve(url, tmp); tmp.replace(p)
            url = str(p)
        return "read_parquet('" + url.replace("'", "''") + "')"   # url is built from the whitelist only

    def _q(self, sql, params=()):
        with self._lock:
            cur = self.con.execute(sql, list(params))
            return [d[0] for d in cur.description], cur.fetchall()

    def _describe(self, layer):
        return [(r[0], r[1]) for r in self._q(f"DESCRIBE SELECT * FROM {self._src(layer)}")[1]]

    def _select(self, layer, include_geometry, extra=""):
        cols = ", ".join(f'"{c}"' for c, _ in self.fields(layer))
        g = "geom::GEOMETRY"
        geo = f", ST_AsGeoJSON({g}) AS __geojson" if include_geometry else ""
        return (f'SELECT "{ID_FIELD}", {cols}, ST_Y(ST_Centroid({g})) AS __lat, ST_X(ST_Centroid({g})) AS __lon{geo}{extra} '
                f"FROM {self._src(layer)}")

    def _run(self, layer, sql, params, include_geometry):
        cols, rows = self._q(sql, params)
        return [_feature(layer, cols, r, include_geometry) for r in rows]

    def find_near(self, layer, lat, lon, radius_miles, limit=None, include_geometry=False):
        lat, lon, r = _check_point(lat, lon, radius_miles)
        m = r * M_PER_MILE; dlat = m / 111_320; dlon = dlat / max(math.cos(math.radians(lat)), 0.01)
        dist = ("ST_Distance(ST_Transform(geom::GEOMETRY, 'EPSG:4326', 'EPSG:3086', always_xy := true), "
                "ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:3086', always_xy := true))")
        sql = (f"SELECT * FROM ({self._select(layer, include_geometry, ', ' + dist + ' AS __dist_m')} "
               "WHERE geom_bbox.xmax >= ? AND geom_bbox.xmin <= ? AND geom_bbox.ymax >= ? AND geom_bbox.ymin <= ?) "
               "WHERE __dist_m <= ? ORDER BY __dist_m LIMIT ?")
        return self._run(layer, sql, [lon, lat, lon - dlon, lon + dlon, lat - dlat, lat + dlat, m, clamp_limit(limit)], include_geometry)

    def features_in_bbox(self, layer, bbox, limit=None, include_geometry=False):
        x1, y1, x2, y2 = _bbox(bbox)
        sql = (f"{self._select(layer, include_geometry)} WHERE geom_bbox.xmax >= ? AND geom_bbox.xmin <= ? "
               "AND geom_bbox.ymax >= ? AND geom_bbox.ymin <= ? "
               "AND ST_Intersects(geom::GEOMETRY, ST_MakeEnvelope(?, ?, ?, ?)) LIMIT ?")
        return self._run(layer, sql, [x1, x2, y1, y2, x1, y1, x2, y2, clamp_limit(limit)], include_geometry)

    def get_feature(self, layer, id, include_geometry=True):
        r = self._run(layer, f'{self._select(layer, include_geometry)} WHERE "{ID_FIELD}" = ? LIMIT 1', [int(id)], include_geometry)
        return r[0] if r else None

    def search_attributes(self, layer, field, value=None, contains=None, limit=None, include_geometry=False):
        f = self.check_field(layer, field)
        if (value is None) == (contains is None): raise ValueError("give exactly one of value or contains")
        cond, p = (f'CAST("{f}" AS VARCHAR) = ?', str(value)) if value is not None else (f'CAST("{f}" AS VARCHAR) ILIKE ?', f"%{contains}%")
        return self._run(layer, f"{self._select(layer, include_geometry)} WHERE {cond} LIMIT ?", [p, clamp_limit(limit)], include_geometry)

    def count_by(self, layer, field, limit=None):
        f = self.check_field(layer, field)
        _, rows = self._q(f'SELECT CAST("{f}" AS VARCHAR) AS v, count(*) AS n FROM {self._src(layer)} GROUP BY 1 ORDER BY n DESC, v LIMIT ?',
                          [clamp_limit(limit)])
        return [{"value": v, "count": n} for v, n in rows]


class PostGISBackend(Backend):
    """Optional: a PostGIS database built by this repo (views sjrwmd.<alias>, geometry in EPSG:3086). Read-only sessions."""
    name = "postgis"
    def __init__(self, dsn: str):
        super().__init__()
        import psycopg
        self.conn = psycopg.connect(dsn, autocommit=True, options="-c default_transaction_read_only=on -c statement_timeout=30000")
        from psycopg import sql
        self.sql = sql

    def _q(self, query, params=()):
        with self._lock, self.conn.cursor() as cur:
            cur.execute(query, params)
            return [d.name for d in cur.description], cur.fetchall()

    def _describe(self, layer):
        _, rows = self._q("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='sjrwmd' AND table_name=%s "
                          "ORDER BY ordinal_position", (layer,))
        if not rows: raise ValueError(f"layer {layer} is not loaded in this database")
        return rows

    def _select(self, layer, include_geometry, extra=None):
        S = self.sql
        cols = S.SQL(", ").join(S.Identifier(c) for c, _ in self.fields(layer))
        parts = [S.SQL("SELECT {id}, {cols}, ST_Y(ST_Transform(ST_Centroid(geom), 4326)) AS __lat, "
                       "ST_X(ST_Transform(ST_Centroid(geom), 4326)) AS __lon").format(id=S.Identifier(ID_FIELD), cols=cols)]
        if include_geometry: parts.append(S.SQL(", ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS __geojson"))
        if extra: parts.append(extra)
        parts.append(S.SQL(" FROM sjrwmd.{t} ").format(t=S.Identifier(check_layer(layer))))
        return S.Composed(parts)

    def _run(self, layer, q, params, include_geometry):
        cols, rows = self._q(q, params)
        return [_feature(layer, cols, r, include_geometry) for r in rows]

    PT = "ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3086)"

    def find_near(self, layer, lat, lon, radius_miles, limit=None, include_geometry=False):
        lat, lon, r = _check_point(lat, lon, radius_miles); S = self.sql
        q = self._select(layer, include_geometry, S.SQL(f", ST_Distance(geom, {self.PT}) AS __dist_m")) + \
            S.SQL(f"WHERE ST_DWithin(geom, {self.PT}, %s) ORDER BY __dist_m LIMIT %s")
        return self._run(layer, q, (lon, lat, lon, lat, r * M_PER_MILE, clamp_limit(limit)), include_geometry)

    def features_in_bbox(self, layer, bbox, limit=None, include_geometry=False):
        x1, y1, x2, y2 = _bbox(bbox)
        q = self._select(layer, include_geometry) + self.sql.SQL(
            "WHERE geom && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 3086) "
            "AND ST_Intersects(geom, ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 3086)) LIMIT %s")
        return self._run(layer, q, (x1, y1, x2, y2, x1, y1, x2, y2, clamp_limit(limit)), include_geometry)

    def get_feature(self, layer, id, include_geometry=True):
        q = self._select(layer, include_geometry) + self.sql.SQL("WHERE {id} = %s LIMIT 1").format(id=self.sql.Identifier(ID_FIELD))
        r = self._run(layer, q, (int(id),), include_geometry)
        return r[0] if r else None

    def search_attributes(self, layer, field, value=None, contains=None, limit=None, include_geometry=False):
        f = self.sql.Identifier(self.check_field(layer, field))
        if (value is None) == (contains is None): raise ValueError("give exactly one of value or contains")
        cond, p = ("{f}::text = %s", str(value)) if value is not None else ("{f}::text ILIKE %s", f"%{contains}%")
        q = self._select(layer, include_geometry) + self.sql.SQL("WHERE " + cond + " LIMIT %s").format(f=f)
        return self._run(layer, q, (p, clamp_limit(limit)), include_geometry)

    def count_by(self, layer, field, limit=None):
        S = self.sql; f = S.Identifier(self.check_field(layer, field))
        q = S.SQL("SELECT {f}::text AS v, count(*) AS n FROM sjrwmd.{t} GROUP BY 1 ORDER BY n DESC, v LIMIT %s").format(
            f=f, t=S.Identifier(check_layer(layer)))
        return [{"value": v, "count": n} for v, n in self._q(q, (clamp_limit(limit),))[1]]


def make_backend() -> Backend:
    dsn = os.environ.get("DATABASE_URL")
    if dsn: return PostGISBackend(dsn)
    # Default: download each layer's GeoParquet once (on first use) to a local cache, then query it locally.
    # SJRWMD_CACHE=0 queries the release URLs directly over HTTP range requests (no disk use, but slower:
    # the files are not spatially sorted, so most row groups must be read).
    if os.environ.get("SJRWMD_CACHE", "1").lower() in ("0", "false", "no"):
        return DuckDBBackend(None)
    return DuckDBBackend(os.environ.get("SJRWMD_CACHE_DIR", "~/.cache/sjrwmd-mcp"))
