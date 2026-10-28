"""Tests against the real published release data (DuckDB backend; downloads to the local cache on first use)."""
import os, pytest
from sjrwmd_mcp import server as s
from sjrwmd_mcp.layers import MAX_LIMIT

ORLANDO = (28.5383, -81.3792)

def test_list_layers():
    r = s.list_layers()
    assert len(r["layers"]) == 15 and "erp" in {l["name"] for l in r["layers"]}
    erp = next(l for l in r["layers"] if l["name"] == "erp")
    assert erp["geometry"] == "polygon" and "county" in erp["fields"] and "geom" not in erp["fields"]

def test_describe_layer():
    r = s.describe_layer("cup_station")
    assert r["features"] == 96498 and any(f["name"] == "prmt_stts" for f in r["fields"])

def test_find_near_sorted_and_within_radius():
    r = s.find_near("cup_station", *ORLANDO, radius_miles=2, limit=20)
    d = [f["distance_miles"] for f in r["results"]]
    assert 0 < len(d) <= 20 and d == sorted(d) and max(d) <= 2

def test_features_in_bbox():
    r = s.features_in_bbox("erp", [-81.40, 28.52, -81.36, 28.56], limit=10)
    assert r["count"] == 10
    for f in r["results"]:
        assert -81.6 < f["centroid"]["lon"] < -81.1

def test_get_feature_roundtrip():
    first = s.search_attributes("management_area", "conservation_area", contains="Three Forks", limit=1)["results"][0]
    r = s.get_feature("management_area", first["id"])["results"]
    assert r["id"] == first["id"] and r["geometry"]["type"] in ("Polygon", "MultiPolygon")

def test_count_by():
    r = s.count_by("erp", "county", limit=5)["results"]
    assert r[0]["count"] >= r[-1]["count"] and sum(x["count"] for x in r) > 40000

def test_limits_and_whitelist():
    assert len(s.count_by("well_completion", "objectid", limit=10_000)["results"]) == MAX_LIMIT
    with pytest.raises(ValueError): s.describe_layer("pg_catalog.pg_authid")
    with pytest.raises(ValueError): s.count_by("erp", "county; drop table x")
    with pytest.raises(ValueError): s.find_near("erp", 28.5, -81.3, radius_miles=500)

def test_injection_value_is_inert():
    r = s.search_attributes("erp", "county", value="Orange' OR '1'='1")
    assert r["count"] == 0

@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="set DATABASE_URL to test the PostGIS backend")
def test_postgis_backend_matches():
    from sjrwmd_mcp.backends import PostGISBackend, DuckDBBackend
    pg = PostGISBackend(os.environ["DATABASE_URL"])
    a = pg.count_by("erp", "county", 3)
    b = s.backend().count_by("erp", "county", 3)
    assert a == b
    near = pg.find_near("cup_station", *ORLANDO, 2, 5)
    assert near and near[0]["distance_miles"] <= 2
    with pytest.raises(Exception): pg._q("CREATE TABLE sjrwmd.x (i int)")   # read-only session
