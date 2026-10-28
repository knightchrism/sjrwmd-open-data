# sjrwmd-open-data

An **open, unofficial mirror** of the St. Johns River Water Management District's (SJRWMD, Florida) public **ArcGIS Online** data
in **PostGIS**, served with open-source tools (pg_featureserv, Martin, MapLibre).

> Not affiliated with or endorsed by SJRWMD. Data: Florida public records, credited to SJRWMD and provided with no warranty.
> See [DATA-LICENSE.md](DATA-LICENSE.md). Code: [MIT](LICENSE).

## What it does
- `esri_inventory.csv` lists every layer in SJRWMD's ArcGIS Online org (230 FeatureServers, 454 layers). `scripts/enumerate_esri.py` regenerates it.
- `harvest.py` loads each layer into a **typed** PostGIS table (`sjrwmd.<service>_<layer>`, columns derived from the Esri field definitions) in EPSG:3086, with a `<table>_4326` view for web use.
  - It pages politely by OBJECTID ranges, with a configurable delay, 2 workers and retries with backoff on 429/5xx.
  - It assembles Esri polygon rings correctly. The server's own GeoJSON output turns holes into separate polygons, which shows up as "nested shells".
  - Polygons that are still invalid under OGC rules (Esri allows self-touching rings) are repaired with `ST_MakeValid` and flagged in `_geom_repaired`.
  - Provenance columns: `_source_url`, `_hub_item_id`, `_fetched_at`, `_source_last_edit`, `_hash`.
  - Incremental: it skips layers whose `lastEditDate`, count and schema are unchanged, otherwise runs a hash-diff upsert plus delete. It is idempotent on rerun.
  - Every run is logged in `meta.harvest_run`.
- `qc/qc.sql` checks count against `returnCountOnly`, validity, null or empty geometry and SRID, and writes the results to `qc.results`.
- `scripts/export.sh` builds a `pg_dump` plus GeoParquet and GeoPackage per layer into `dist/`.
- `scripts/build_tiles.sh` and `docs/` build PMTiles and the static MapLibre web map.
- Phase 1 layers get friendly views (`sjrwmd.erp`, `sjrwmd.cup_station`, …), configured in `layers.yaml`.

## Quickstart (Docker)
```bash
cp .env.example .env            # change the passwords; set PG_HOST_PORT/PGPORT if 5432 is taken
docker compose up -d            # PostGIS 17-3.5, pg_featureserv :9000, Martin :3000
python -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a; . ./.env; set +a
.venv/bin/python harvest.py     # full run takes a few hours the first time; reruns skip unchanged layers
psql -f qc/qc.sql
docker compose restart martin   # Martin discovers new tables at startup
```
Options: `--only erp cup_station`, `--force`, `--limit N`.

## Windows (C:\dev, outside OneDrive)
```powershell
cd C:\dev; git clone https://github.com/knightchrism/sjrwmd-open-data; cd sjrwmd-open-data
copy .env.example .env; docker compose up -d
py -m venv .venv; .venv\Scripts\pip install -r requirements.txt
Get-Content .env | % { if ($_ -match '^(\w+)=(.*)$') { Set-Item "env:$($matches[1])" $matches[2] } }
.venv\Scripts\python harvest.py
```

## Automation
`.github/workflows/weekly-update.yml` is **disabled**: it is manual-trigger only, gated on the `HARVEST_ENABLED` variable, and has no schedule until hosting is chosen.
