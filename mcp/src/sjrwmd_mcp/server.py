"""sjrwmd-mcp: a read-only MCP server for 15 St. Johns River Water Management District GIS layers.

Data: SJRWMD public records via an unofficial mirror (https://knightchrism.github.io/sjrwmd-open-data/), no warranty.
Backends: DuckDB over the release GeoParquet (default) or PostGIS (set DATABASE_URL).
"""
from __future__ import annotations
from typing import Optional
from mcp.server.fastmcp import FastMCP
from .backends import make_backend
from .layers import DEFAULT_LIMIT, LAYERS, MAX_LIMIT, RELEASE, check_layer

CREDIT = ("Data: St. Johns River Water Management District (Florida public records), via an unofficial mirror "
          "(https://knightchrism.github.io/sjrwmd-open-data/). Not endorsed by SJRWMD; no warranty. See https://www.sjrwmd.com/disclaimer/")

mcp = FastMCP("sjrwmd", instructions=(
    "Query 15 GIS layers from Florida's St. Johns River Water Management District: permits (ERP, consumptive use, wells, "
    "easements, reuse), monitoring stations, district lands, 2020 land use and streams. Coordinates are WGS84 lat/lon; "
    "distances are miles. Call list_layers first, then describe_layer to learn field names. Results return attributes and a "
    f"centroid; ask for include_geometry only when needed. Limits default to {DEFAULT_LIMIT}, max {MAX_LIMIT}. "
    "Always tell the user the data is an unofficial copy of SJRWMD data."))
_backend = None

def backend():
    global _backend
    if _backend is None: _backend = make_backend()
    return _backend

def _wrap(results, **meta):
    return {**meta, "count": len(results) if isinstance(results, list) else (1 if results else 0), "results": results, "credit": CREDIT}

@mcp.tool()
def list_layers() -> dict:
    """List the 15 available layers with geometry type, feature count and field names."""
    b = backend()
    return {"backend": b.name, "layers": [
        {"name": k, "title": t, "geometry": g, "features": n, "about": why, "fields": [c for c, _ in b.fields(k)]}
        for k, (t, g, n, why) in LAYERS.items()], "credit": CREDIT}

@mcp.tool()
def describe_layer(layer: str) -> dict:
    """Describe one layer: title, geometry, feature count, fields with types, and source/download links."""
    t, g, n, why = LAYERS[check_layer(layer)]
    return {"name": layer, "title": t, "geometry": g, "features": n, "about": why, "id_field": "source_oid",
            "fields": [{"name": c, "type": str(ty)} for c, ty in backend().fields(layer)],
            "downloads": {f: f"{RELEASE}{layer}.{f}" for f in ("parquet", "gpkg", "csv.zip")}, "credit": CREDIT}

@mcp.tool()
def find_near(layer: str, lat: float, lon: float, radius_miles: float = 1.0, limit: int = DEFAULT_LIMIT,
              include_geometry: bool = False) -> dict:
    """Features of a layer within radius_miles (max 50) of a WGS84 lat/lon, nearest first, with distance_miles."""
    return _wrap(backend().find_near(layer, lat, lon, radius_miles, limit, include_geometry), layer=layer, lat=lat, lon=lon, radius_miles=radius_miles)

@mcp.tool()
def features_in_bbox(layer: str, bbox: list[float], limit: int = DEFAULT_LIMIT, include_geometry: bool = False) -> dict:
    """Features of a layer intersecting bbox = [min_lon, min_lat, max_lon, max_lat] (WGS84, max 25 square degrees)."""
    return _wrap(backend().features_in_bbox(layer, bbox, limit, include_geometry), layer=layer, bbox=bbox)

@mcp.tool()
def get_feature(layer: str, id: int, include_geometry: bool = True) -> dict:
    """Get one feature by its id (source_oid), including GeoJSON geometry by default."""
    return _wrap(backend().get_feature(layer, id, include_geometry), layer=layer, id=id)

@mcp.tool()
def search_attributes(layer: str, field: str, value: Optional[str] = None, contains: Optional[str] = None,
                      limit: int = DEFAULT_LIMIT, include_geometry: bool = False) -> dict:
    """Find features where a field equals value, or contains a substring (case-insensitive). Give exactly one."""
    return _wrap(backend().search_attributes(layer, field, value, contains, limit, include_geometry), layer=layer, field=field)

@mcp.tool()
def count_by(layer: str, field: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Count features grouped by a field's values, most common first (e.g. erp by county or prmt_stts)."""
    return _wrap(backend().count_by(layer, field, limit), layer=layer, field=field)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
