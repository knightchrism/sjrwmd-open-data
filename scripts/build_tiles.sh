#!/usr/bin/env bash
# Build one PMTiles archive per geometry layer from PostGIS (<table>_4326 views) with tippecanoe.
# Needs ogr2ogr, tippecanoe >= 2.17 and libpq env vars. Output: tiles-build/<table>.pmtiles (git-ignored).
# Tiles are capped at about 500 KB (-M 500000); dense layers are thinned or coalesced at low zooms.
set -euo pipefail
OUT=${1:-tiles-build}; mkdir -p "$OUT"; TMP=$(mktemp -d)
PG="PG:dbname=${PGDATABASE} host=${PGHOST} port=${PGPORT} user=${PGUSER} password=${PGPASSWORD}"
cols() { psql -XAt -c "select string_agg(quote_ident(column_name), ',' order by ordinal_position) from information_schema.columns where table_schema='sjrwmd' and table_name='${1}_4326' and column_name not like '\\_%'"; }
psql -XAt -F' ' -c "select name, geometry_type from meta.layer_registry where last_status='ok' and geometry_type like 'esriGeometry%' order by name" |
while read -r t g; do
  [ -s "$OUT/$t.pmtiles" ] && [ "${REBUILD:-0}" != 1 ] && continue
  ogr2ogr -f GeoJSONSeq "$TMP/$t.geojsonl" "$PG" "sjrwmd.${t}_4326" -lco RS=NO -lco COORDINATE_PRECISION=6 \
    -sql "select $(cols "$t") from sjrwmd.${t}_4326" 2>/dev/null || { echo "export failed: $t"; continue; }
  case "$g" in
    esriGeometryPoint|esriGeometryMultipoint) Z="-Z6 -z14 --drop-densest-as-needed -r1" ;;
    esriGeometryPolyline) Z="-Z6 -z14 --drop-densest-as-needed --simplification=4" ;;
    *) Z="-Z6 -z14 --coalesce-densest-as-needed --detect-shared-borders --simplification=4" ;;
  esac
  tippecanoe -q -f -o "$OUT/$t.pmtiles" -l "$t" $Z --extend-zooms-if-still-dropping -M 500000 -O 200000 "$TMP/$t.geojsonl" 2>>"$OUT/tippecanoe.log" || echo "tiles failed: $t"
  rm -f "$TMP/$t.geojsonl"
done
rm -rf "$TMP"; du -sh "$OUT"
