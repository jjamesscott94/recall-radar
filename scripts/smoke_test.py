"""End-to-end smoke test: connect to the MCP server over stdio, list tools,
and exercise a few tool calls."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "recall_radar.server"],
        env=None,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            # dataset_stats
            res = await session.call_tool("dataset_stats", {})
            stats = json.loads(res.content[0].text)
            print("\nSTATS: total=%s enriched=%s by_class=%s" % (
                stats["total_active_recalls"], stats["enriched"], stats["by_classification"]))

            # search_recalls
            res = await session.call_tool("search_recalls", {"query": "listeria", "limit": 3})
            hits = json.loads(res.content[0].text)
            print("\nSEARCH 'listeria' -> %d results; first firm=%s" % (
                len(hits), hits[0]["recalling_firm"] if hits else None))

            # get_recall
            res = await session.call_tool("get_recall", {"recall_id": "93920"})
            rec = json.loads(res.content[0].text)
            print("\nGET 93920 -> firm=%s class=%s" % (rec["recalling_firm"], rec["classification"]))

            # brands_to_avoid
            res = await session.call_tool("brands_to_avoid", {})
            brands = json.loads(res.content[0].text)
            print("\nBRANDS_TO_AVOID -> %d firms; top=%s" % (
                len(brands), brands[0]["company"] if brands else None))

            # list_active_recalls (Class I)
            res = await session.call_tool("list_active_recalls", {"classification": "Class I", "limit": 5})
            ci = json.loads(res.content[0].text)
            print("\nCLASS I -> %d results" % len(ci))

            print("\nALL TOOL CALLS OK")


if __name__ == "__main__":
    asyncio.run(main())
