"""The whitelist: the only layers (and, at runtime, the only fields) the server will query."""
import os

RELEASE = os.environ.get("SJRWMD_RELEASE_URL",
                         "https://github.com/knightchrism/sjrwmd-open-data/releases/download/data-2026-10-28/")
DEFAULT_LIMIT, MAX_LIMIT = 50, 500
ID_FIELD = "source_oid"
HIDDEN = {"geom", "geom_bbox", "geometry", "_hash", "_geom_repaired"}

# alias: (title, geometry, features, why)
LAYERS = {
    "erp": ("Environmental Resource Permits", "polygon", 96577, "Permit areas with permit numbers, dates and status."),
    "cup_boundary": ("Consumptive Use Permit boundaries", "polygon", 24462, "Water-use permit project boundaries."),
    "conservation_easement": ("Regulatory conservation easements", "polygon", 13304, "Recorded permit conservation easements."),
    "management_area": ("District management areas", "polygon", 133, "District-managed conservation lands, with manager and acres."),
    "land_use_2020": ("Land cover / land use 2020", "polygon", 309325, "District land use/land cover (FLUCCS codes: lucode, lccode)."),
    "cup_station": ("CUP wells & withdrawal points", "point", 96498, "Permitted wells and withdrawal points."),
    "well_completion": ("Well completion permits", "point", 20438, "District-issued well construction permits."),
    "edr_station": ("Monitoring stations (EDR)", "point", 4879, "Hydrologic and water-quality monitoring stations."),
    "st2025_surface_water": ("2025 Status & Trends: surface water", "point", 2691, "2025 Status & Trends surface-water stations."),
    "st2025_groundwater": ("2025 Status & Trends: groundwater", "point", 1592, "2025 Status & Trends groundwater stations."),
    "stream_flowpath": ("Streams (1:24K flowpaths)", "line", 105354, "District 1:24K stream network."),
    "reuse_line": ("Reclaimed-water lines", "line", 50108, "Reclaimed-water lines reported to the district."),
    "management_area_road": ("Management-area roads", "line", 1592, "Roads on district lands."),
    "management_area_trail": ("Management-area trails", "line", 401, "Public recreation trails on district lands."),
    "ufa_potentiometric_2010": ("Upper Floridan potentiometric surface (2010)", "line", 141, "Sep 2010 Upper Floridan aquifer contours."),
}

def check_layer(layer: str) -> str:
    if layer not in LAYERS:
        raise ValueError(f"unknown layer {layer!r}; choose one of: {', '.join(LAYERS)}")
    return layer

def clamp_limit(limit) -> int:
    try: n = int(limit) if limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError): n = DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))

def parquet_url(layer: str) -> str:
    return f"{RELEASE}{check_layer(layer)}.parquet"
