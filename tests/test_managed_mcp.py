import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _call(params, tool, arguments):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            assert not result.isError, result.content
            payload = result.structuredContent or json.loads(result.content[0].text)
            return payload.get("result", payload) if isinstance(payload, dict) else payload


def test_managed_job_survives_mcp_restart(tmp_path):
    base = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(
        command=sys.executable, args=[str(base / "server.py")],
        env={"LOCAL_RESEARCH_ROOT": str(tmp_path),
             "LOCAL_RESEARCH_STATE_DIR": str(tmp_path / "state"),
             "LOCAL_RESEARCH_ALLOW_EXEC": "1"})
    job_id = None
    try:
        started = asyncio.run(_call(params, "start_managed_process", {
            "argv": [sys.executable, "-u", "-c",
                     "import time; print('persisted', flush=True); time.sleep(60)"],
            "cwd": str(tmp_path)}))
        job_id = started["job_id"]
        for _ in range(50):
            log = asyncio.run(_call(params, "read_managed_process_log", {"job_id": job_id}))
            if "persisted" in log["output"]:
                break
            time.sleep(0.1)
        assert "persisted" in log["output"]
        listed = asyncio.run(_call(params, "list_managed_processes", {}))
        assert any(item["job_id"] == job_id and item["state"] == "running" for item in listed)
        stopped = asyncio.run(_call(params, "stop_managed_process", {"job_id": job_id}))
        assert stopped["state"] == "stopped"
    finally:
        if job_id:
            # Also clean up if the MCP tool assertion above fails.
            from managed_processes import ManagedProcessManager
            from project_state import ProjectState
            manager = ManagedProcessManager(ProjectState(tmp_path, tmp_path / "state").directory)
            manager.stop(job_id)
