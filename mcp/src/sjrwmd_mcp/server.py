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

_LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"cache-control", b"no-store"),
]

def _csv_env(name: str) -> list[str]:
    import os
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]

def transport_security_from_env():
    """DNS-rebinding / Host-header protection stays ON. Localhost is always allowed; add the names clients use to reach
    the server (k8s Service name, public ingress host) via SJRWMD_MCP_ALLOWED_HOSTS / SJRWMD_MCP_ALLOWED_ORIGINS
    (comma-separated; "host:*" matches any port)."""
    from mcp.server.transport_security import TransportSecuritySettings
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_LOCAL_HOSTS + _csv_env("SJRWMD_MCP_ALLOWED_HOSTS"),
        allowed_origins=_LOCAL_ORIGINS + _csv_env("SJRWMD_MCP_ALLOWED_ORIGINS"))

def with_security_headers(app):
    """ASGI wrapper that adds conservative security headers to every HTTP response."""
    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message.get("headers", [])}
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [h for h in SECURITY_HEADERS if h[0] not in names]
            await send(message)
        return await app(scope, receive, send_with_headers)
    return wrapped

def main():
    """stdio by default; set SJRWMD_MCP_TRANSPORT=streamable-http (plus HOST/PORT) to serve http://HOST:PORT/mcp."""
    import os
    transport = os.environ.get("SJRWMD_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        return mcp.run(transport=transport)
    mcp.settings.host = os.environ.get("SJRWMD_MCP_HOST", "127.0.0.1")
    mcp.settings.port = int(os.environ.get("SJRWMD_MCP_PORT", "8000"))
    mcp.settings.transport_security = transport_security_from_env()
    if transport != "streamable-http":
        return mcp.run(transport=transport)
    import uvicorn
    uvicorn.run(with_security_headers(mcp.streamable_http_app()), host=mcp.settings.host, port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower(), server_header=False, proxy_headers=False)

if __name__ == "__main__":
    main()
