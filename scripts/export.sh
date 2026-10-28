#!/usr/bin/env bash
# Build the per-layer download files published as GitHub release assets (one set per selected layer, named by alias):
#   <alias>.gpkg       GeoPackage, EPSG:3086 (Florida GDL Albers, meters), with provenance columns
#   <alias>.parquet    GeoParquet, EPSG:4326, ZSTD
#   <alias>.csv.zip    CSV with WKT geometry (EPSG:4326)
# Needs ogr2ogr (GDAL >= 3.8 with the Parquet driver), python3, and libpq env vars. Output: dist/ (git-ignored).
set -euo pipefail
OUT=${1:-dist}; mkdir -p "$OUT"; TMP=$(mktemp -d)
PG="PG:dbname=${PGDATABASE} host=${PGHOST} port=${PGPORT} user=${PGUSER} password=${PGPASSWORD}"
psql -XAt -F' ' -c "select name, alias from meta.layer_registry where last_status='ok' and alias is not null order by alias" |
while read -r t a; do
  ogr2ogr -f GPKG "$OUT/$a.gpkg" "$PG" "sjrwmd.$t" -nln "$a" -overwrite
  ogr2ogr -f Parquet "$OUT/$a.parquet" "$PG" "sjrwmd.${t}_4326" -nln "$a" -lco COMPRESSION=ZSTD -overwrite
  ogr2ogr -f CSV "$TMP/$a.csv" "$PG" "sjrwmd.${t}_4326" -lco GEOMETRY=AS_WKT -overwrite
  python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED,compresslevel=9).write(sys.argv[2],sys.argv[3])" "$OUT/$a.csv.zip" "$TMP/$a.csv" "$a.csv"
  rm "$TMP/$a.csv"
  echo "$a done"
done
rm -rf "$TMP"; (cd "$OUT" && sha256sum *.gpkg *.parquet *.csv.zip > SHA256SUMS); du -sh "$OUT"
