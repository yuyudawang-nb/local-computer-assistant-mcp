"""Durable project tools and isolated worktree behavior."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_state import ProjectState
from worktrees import Worktrees


def test_tasks_and_memories_survive_new_instance(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    first = ProjectState(root, tmp_path / "state")
    task = first.create_task("Repair ROS bridge", "Verify odometry topic")
    first.update_task(task["id"], "in_progress", "Inspected launch file")
    memory = first.save_memory("odom", "Use /mavros/local_position/odom", "launch")
    second = ProjectState(root, tmp_path / "state")
    loaded = second.get_task(task["id"])
    assert loaded["status"] == "in_progress" and loaded["events"][0]["note"] == "Inspected launch file"
    assert second.search_memories("mavros")[0]["id"] == memory["id"]
    assert second.export_context()["tasks"][0]["id"] == task["id"]
    assert second.delete_memory(memory["id"])["deleted"]
    assert not second.search_memories("mavros")
    assert oct(second.path.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ValueError):
        second.update_task(task["id"], "invalid")


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def test_worktree_isolation_and_refuse_dirty_removal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.txt").write_text("original\n")
    _git(root, "add", "a.txt")
    _git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
    state = ProjectState(root, tmp_path / "state")
    trees = Worktrees(root, state.directory)
    info = trees.create("bridge-fix")
    worktree = Path(info["path"])
    assert info["branch"].startswith("codex/bridge-fix-")
    assert (worktree / "a.txt").read_text() == "original\n"
    assert trees.resolve(str(worktree)) == worktree
    with pytest.raises(ValueError):
        trees.resolve(str(tmp_path / "outside"))
    (worktree / "a.txt").write_text("changed\n")
    assert (root / "a.txt").read_text() == "original\n"
    with pytest.raises(ValueError, match="changes"):
        trees.remove_clean(str(worktree))
    (worktree / "a.txt").write_text("original\n")
    assert trees.remove_clean(str(worktree))["removed"] == str(worktree)
    assert not worktree.exists()
