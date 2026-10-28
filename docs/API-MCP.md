# sjrwmd-mcp: query the SJRWMD mirror from an AI assistant

`sjrwmd-mcp` is a read-only [Model Context Protocol](https://modelcontextprotocol.io) server for the 15 layers in this mirror.
Any MCP client (GitHub Copilot in VS Code, Claude Desktop, Cursor, …) can call it to answer spatial questions about
St. Johns River Water Management District permits, stations, district lands, land use and streams.

> The data is an **unofficial** copy of SJRWMD public records (Ch. 119, F.S.), credited to SJRWMD and provided with no warranty.
> Every tool result includes a `credit` field saying so. Check important answers against https://data-floridaswater.opendata.arcgis.com.

## Use with GitHub Copilot in VS Code (featured)
1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (provides `uvx`). Use VS Code with GitHub Copilot.
2. Clone this repo and open it in VS Code; it ships [`.vscode/mcp.json`](../.vscode/mcp.json). Or add this to any workspace's `.vscode/mcp.json`:
   ```json
   {
     "servers": {
       "sjrwmd": {
         "type": "stdio",
         "command": "uvx",
         "args": ["--from", "git+https://github.com/knightchrism/sjrwmd-open-data#subdirectory=mcp", "sjrwmd-mcp"]
       }
     }
   }
   ```
   Click **Start** above the entry (or run *MCP: List Servers*).
3. Open Copilot Chat (Ctrl+Alt+I / ⌃⌘I) and choose **Agent** mode.
4. Click the tools icon and check the **sjrwmd** tools. Approve the first tool call when asked.
5. Ask, for example (outputs are from the recorded runs in [`docs/demo/`](demo/)):
   - "Which permitted water-use wells are within 2 miles of downtown DeLand?" → `find_near(cup_station, 29.0283, -81.3031, 2)`: 25 wells (limit reached), nearest 0.161 mi, with station type, status and permit project.
   - "Which counties have the most ERP permits?" → `count_by(erp, county)`: Duval 15,438, Brevard 12,520, Orange 12,382, Volusia 9,946, St. Johns 8,195, …
   - "Show the trails in the Lake Norris Conservation Area." → `search_attributes(management_area, conservation_area, contains="Lake Norris")` then `features_in_bbox(management_area_trail, …)`: 6 trail segments with blaze, allowed uses and miles.
   - "Which monitoring stations are within 3 miles of Lake George?" → `find_near(edr_station, 29.28, -81.60, 3)`: station names, category, status, county.

See them rendered on the site: https://knightchrism.github.io/sjrwmd-open-data/#demo

## Other clients
Claude Desktop (`claude_desktop_config.json`) and Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json`):
```json
{ "mcpServers": { "sjrwmd": { "command": "uvx",
  "args": ["--from", "git+https://github.com/knightchrism/sjrwmd-open-data#subdirectory=mcp", "sjrwmd-mcp"] } } }
```
Manual: `uvx --from "git+https://github.com/knightchrism/sjrwmd-open-data#subdirectory=mcp" sjrwmd-mcp`
or `pip install "git+https://github.com/knightchrism/sjrwmd-open-data#subdirectory=mcp"` then `sjrwmd-mcp`. Not published on PyPI.

A public web chat on the site would need a hosted model, so it is not included.

## Tools
| Tool | Arguments | Returns |
|---|---|---|
| `list_layers` | – | 15 layers: name, title, geometry, features, fields |
| `describe_layer` | `layer` | fields with types, id field, download URLs |
| `find_near` | `layer, lat, lon, radius_miles=1 (≤50), limit=50, include_geometry=false` | features nearest first, with `distance_miles` |
| `features_in_bbox` | `layer, bbox=[min_lon,min_lat,max_lon,max_lat] (≤25 sq°), limit, include_geometry` | intersecting features |
| `get_feature` | `layer, id, include_geometry=true` | one feature |
| `search_attributes` | `layer, field, value` **or** `contains`, `limit`, `include_geometry` | exact or case-insensitive substring matches |
| `count_by` | `layer, field, limit` | `[{value, count}]`, most common first |

Results are GeoJSON-lite: `{layer, id, centroid:{lat,lon}, properties, [distance_miles], [geometry]}`. `id` is `source_oid` (the layer's OBJECTID).
Limits default to 50, max 500. Layers: `erp, cup_boundary, conservation_easement, management_area, land_use_2020, cup_station, well_completion,
edr_station, st2025_surface_water, st2025_groundwater, stream_flowpath, reuse_line, management_area_road, management_area_trail, ufa_potentiometric_2010`.

## Backends
| | DuckDB (default) | PostGIS (optional) |
|---|---|---|
| Needs | nothing; DuckDB `spatial` + `httpfs` extensions load automatically | a database built by this repo |
| Data | GeoParquet from the GitHub release | views `sjrwmd.<layer>` |
| Enable | default | `DATABASE_URL=postgresql://sjrwmd_reader:…@host:5432/sjrwmd` (`pip install "sjrwmd-mcp[postgis]"`) |

DuckDB downloads each layer's GeoParquet on first use to `~/.cache/sjrwmd-mcp` (`SJRWMD_CACHE_DIR` to change), then queries locally:
an ERP `find_near` took 1.3 s cached versus 67 s straight from the release URL, because the files are not spatially sorted.
`SJRWMD_CACHE=0` queries the release URLs directly over HTTP range requests with no disk use. `SJRWMD_RELEASE_URL` points at a different release.

## Safety
- Read-only: fixed SQL templates only; there is no free-form SQL tool.
- Layer and field names are checked against a whitelist (the 15 layers and their real columns, minus geometry and internal `_` columns).
- All user values are bound parameters. Tests confirm `county = "Orange' OR '1'='1"` returns 0 rows and `count_by(erp, "county; drop table x")` is rejected.
- PostGIS sessions run with `default_transaction_read_only=on` and a 30 s `statement_timeout`; use the `sjrwmd_reader` role.
- Radius ≤ 50 miles, bbox ≤ 25 square degrees, results ≤ 500.

## Development
```bash
cd mcp && python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest -q                      # real release data; set DATABASE_URL to also test PostGIS
.venv/bin/python scripts/record_demo.py ../docs/demo   # re-record the site's demo runs
```
