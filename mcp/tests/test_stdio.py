"""Smoke test: start the server as a subprocess and talk to it over stdio with the official MCP client."""
import json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_stdio_smoke():
    params = StdioServerParameters(command=sys.executable, args=["-m", "sjrwmd_mcp.server"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "sjrwmd"
            names = {t.name for t in (await session.list_tools()).tools}
            assert names == {"list_layers", "describe_layer", "find_near", "features_in_bbox", "get_feature", "search_attributes", "count_by"}
            res = await session.call_tool("find_near", {"layer": "edr_station", "lat": 28.5383, "lon": -81.3792, "radius_miles": 3, "limit": 5})
            assert not res.isError
            data = json.loads(res.content[0].text)
            assert 0 < data["count"] <= 5 and "St. Johns" in data["credit"]
