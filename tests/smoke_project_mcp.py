"""Real stdio round-trip for durable tasks, memories and review UI resource."""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def data(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


async def main():
    base = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "repo"
        root.mkdir()
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        (root / "demo.txt").write_text("hello\n")
        subprocess.run(["git", "-C", str(root), "add", "demo.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        "commit", "-qm", "initial"], check=True)
        params = StdioServerParameters(
            command=sys.executable, args=[str(base / "server.py")],
            env={"LOCAL_RESEARCH_ROOT": str(root), "LOCAL_RESEARCH_STATE_DIR": str(Path(temp) / "state"),
                 "LOCAL_RESEARCH_ALLOW_EXEC": "1"})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                assert "describe outcomes, not tool names" in initialized.instructions
                resources = await session.list_resources()
                assert any(str(item.uri) == "ui://local-research/review.html" for item in resources.resources)
                ui = await session.read_resource("ui://local-research/review.html")
                assert "Git 差异审阅" in ui.contents[0].text
                task = data(await session.call_tool("task_create", {"title": "Test task"}))
                memory = data(await session.call_tool("memory_save", {"title": "Topic", "content": "test fact"}))
                context = data(await session.call_tool("project_context"))
                assert context["tasks"][0]["id"] == task["id"]
                assert context["memories"][0]["id"] == memory["id"]
                tree = data(await session.call_tool("worktree_create", {"name": "test-task", "task_id": task["id"]}))
                assert tree["branch"].startswith("codex/")
                listing = data(await session.call_tool("list_files", {"path": tree["path"]}))
                assert any(entry["name"] == "demo.txt" for entry in listing["entries"])
                patch = "diff --git a/demo.txt b/demo.txt\n--- a/demo.txt\n+++ b/demo.txt\n@@ -1 +1 @@\n-hello\n+changed\n"
                applied = data(await session.call_tool("apply_unified_patch", {"patch": patch, "workspace": tree["path"]}))
                assert applied["applied"]
                assert (root / "demo.txt").read_text() == "hello\n"
                review = data(await session.call_tool("review_panel", {"workspace": tree["path"]}))
                assert "+changed" in review["unstaged_diff"]
                restored = data(await session.call_tool("run_command", {
                    "argv": ["git", "restore", "--", "demo.txt"], "cwd": tree["path"]}))
                assert restored["exit_code"] == 0
                data(await session.call_tool("worktree_remove_clean", {"path": tree["path"]}))
                print("Project MCP smoke passed: tasks, memories, worktrees, review UI", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
