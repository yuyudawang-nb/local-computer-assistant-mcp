"""Read-only live X11/MCP check; never clicks or types on the user's desktop."""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    base = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.update({"DISPLAY": env.get("DISPLAY") or ":0",
                "LOCAL_RESEARCH_ROOT": str(base),
                "LOCAL_RESEARCH_ALLOW_DESKTOP": "1"})
    params = StdioServerParameters(command=sys.executable, args=[str(base / "server.py")], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            info = await session.call_tool("desktop_info")
            assert not info.isError
            shot = await session.call_tool("desktop_screenshot", {"monitor": 0})
            assert not shot.isError and len(shot.content) == 1
            assert shot.content[0].type == "image" and shot.content[0].mimeType == "image/jpeg"
            print("Desktop MCP smoke passed: monitor info and JPEG image")


if __name__ == "__main__":
    asyncio.run(main())
