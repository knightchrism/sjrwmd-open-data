#!/usr/bin/env bash
# Build local release artifacts: a pg_dump of the sjrwmd/meta/qc schemas plus GeoParquet and GeoPackage per layer.
# Needs: pg_dump, ogr2ogr (GDAL >= 3.8 with the Parquet driver), libpq env vars (see .env.example).
# Output: dist/ (git-ignored). Nothing is uploaded.
set -euo pipefail
OUT=${1:-dist}; mkdir -p "$OUT"/geoparquet "$OUT"/gpkg
PG="PG:dbname=${PGDATABASE} host=${PGHOST} port=${PGPORT} user=${PGUSER} password=${PGPASSWORD}"
pg_dump -Fc -n sjrwmd -n meta -n qc --no-owner -f "$OUT/sjrwmd.dump"
psql -XAt -c "select name from meta.layer_registry where last_status='ok' order by name" | while read -r t; do
  ogr2ogr -f Parquet "$OUT/geoparquet/$t.parquet" "$PG" "sjrwmd.$t" -lco COMPRESSION=ZSTD -overwrite 2>>"$OUT/export.log" || echo "parquet failed: $t" >>"$OUT/export.log"
  ogr2ogr -f GPKG "$OUT/gpkg/$t.gpkg" "$PG" "sjrwmd.$t" -nln "$t" -overwrite 2>>"$OUT/export.log" || echo "gpkg failed: $t" >>"$OUT/export.log"
done
( cd "$OUT" && sha256sum sjrwmd.dump geoparquet/* gpkg/* > SHA256SUMS )
du -sh "$OUT"/sjrwmd.dump "$OUT"/geoparquet "$OUT"/gpkg
