"""Record the site's demo: run real MCP tool calls over stdio and save the exact arguments and JSON results to docs/demo/."""
import asyncio, datetime as dt, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEMOS = [
  ("water-use-near-deland", "Which permitted water-use wells are within 2 miles of downtown DeLand?",
   [("find_near", {"layer": "cup_station", "lat": 29.0283, "lon": -81.3031, "radius_miles": 2, "limit": 25})]),
  ("erp-lake-eola", "What Environmental Resource Permits are on file around Lake Eola in downtown Orlando?",
   [("features_in_bbox", {"layer": "erp", "bbox": [-81.385, 28.538, -81.365, 28.552], "limit": 25, "include_geometry": True})]),
  ("stations-lake-george", "Which monitoring stations are within 3 miles of Lake George?",
   [("find_near", {"layer": "edr_station", "lat": 29.28, "lon": -81.60, "radius_miles": 3, "limit": 25})]),
  ("trails-in-management-area", "Find the Lake Norris Conservation Area, then show the trails inside it.",
   [("search_attributes", {"layer": "management_area", "field": "conservation_area", "contains": "Lake Norris", "limit": 1, "include_geometry": True}),
    ("features_in_bbox", {"layer": "management_area_trail", "bbox": "FROM_PREVIOUS", "limit": 50, "include_geometry": True})]),
  ("erp-by-county", "Which counties have the most Environmental Resource Permits?",
   [("count_by", {"layer": "erp", "field": "county", "limit": 10})]),
]

def bbox_of(geom):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)): xs.append(c[0]); ys.append(c[1])
        else: [walk(x) for x in c]
    walk(geom["coordinates"]); return [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]

async def main(out="docs/demo"):
    params = StdioServerParameters(command=sys.executable, args=["-m", "sjrwmd_mcp.server"])
    index = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            for slug, q, calls in DEMOS:
                rec, prev = {"slug": slug, "question": q, "server": f"{init.serverInfo.name} {init.serverInfo.version}",
                             "recorded_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "calls": []}, None
                for tool, args in calls:
                    args = dict(args)
                    if args.get("bbox") == "FROM_PREVIOUS": args["bbox"] = bbox_of(prev["results"][0]["geometry"])
                    res = await s.call_tool(tool, args)
                    prev = json.loads(res.content[0].text)
                    rec["calls"].append({"tool": tool, "arguments": args, "is_error": res.isError, "result": prev})
                json.dump(rec, open(f"{out}/{slug}.json", "w"), indent=1)
                index.append({"slug": slug, "question": q})
                print(slug, [c["result"].get("count") for c in rec["calls"]])
    json.dump(index, open(f"{out}/index.json", "w"), indent=1)

asyncio.run(main(*sys.argv[1:]))
