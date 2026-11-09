"""Exercise a real stdio JSON-RPC exchange with the running MCP server."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    base = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(command=sys.executable, args=[str(base / "server.py")],
                                   env={"LOCAL_RESEARCH_ROOT": str(base),
                                        "LOCAL_RESEARCH_ALLOW_EXEC": "1"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            assert {"search_topic", "research_and_plan", "read_source", "machine_profile",
                    "list_files", "read_file", "search_files", "run_command", "start_process",
                    "read_process_output", "send_process_input", "stop_process",
                    "start_managed_process", "list_managed_processes", "managed_process_status",
                    "read_managed_process_log", "stop_managed_process",
                    "task_create", "task_list", "task_get", "task_update", "worktree_create",
                    "worktree_list", "worktree_remove_clean", "memory_save", "memory_search",
                    "memory_delete", "project_context", "review_panel"} <= names
            profile = await session.call_tool("machine_profile")
            profile_data = profile.structuredContent or json.loads(profile.content[0].text)
            assert not profile.isError and "architecture" in profile_data
            command = await session.call_tool("run_command", {"argv": ["pwd"]})
            command_data = command.structuredContent or json.loads(command.content[0].text)
            assert not command.isError and str(base) in command_data["stdout"]
            result = await session.call_tool("search_topic", {"query": "mcp server",
                                                               "categories": ["community"],
                                                               "limit_per_category": 1})
            result_data = result.structuredContent or json.loads(result.content[0].text)
            assert not result.isError and "community" in result_data["categories"]
            print("MCP stdio smoke passed:", sorted(names), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
