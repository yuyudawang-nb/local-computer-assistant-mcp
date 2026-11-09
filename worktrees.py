"""Managed Git worktrees for isolated local MCP changes."""

from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path


def _git(root: Path, *args: str, timeout: int = 20) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                       text=True, errors="replace", timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr[:2000] or "Git operation failed")
    return p.stdout


class Worktrees:
    def __init__(self, root: Path, state_dir: Path):
        self.root = root.resolve()
        self.directory = state_dir / "worktrees"

    def list(self) -> list[dict]:
        output = _git(self.root, "worktree", "list", "--porcelain")
        result = []
        for block in output.strip().split("\n\n"):
            if not block:
                continue
            fields = {}
            for line in block.splitlines():
                key, _, value = line.partition(" ")
                fields[key] = value
            path = Path(fields["worktree"]).resolve()
            result.append({"path": str(path), "branch": fields.get("branch", ""),
                           "head": fields.get("HEAD", ""), "managed": path.is_relative_to(self.directory)})
        return result

    def resolve(self, path: str) -> Path:
        candidate = Path(path).expanduser().resolve()
        if candidate == self.root:
            return candidate
        if not candidate.is_relative_to(self.directory):
            raise ValueError("Worktree is outside the managed directory")
        if str(candidate) not in {entry["path"] for entry in self.list() if entry["managed"]}:
            raise ValueError("Unknown managed worktree")
        return candidate

    def create(self, name: str) -> dict:
        slug = name.strip().lower().replace("_", "-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", slug):
            raise ValueError("Name must be 1-40 lowercase letters, digits or hyphens")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        suffix = uuid.uuid4().hex[:6]
        branch = f"codex/{slug}-{suffix}"
        path = self.directory / f"{slug}-{suffix}"
        _git(self.root, "worktree", "add", "-b", branch, str(path), "HEAD", timeout=60)
        return {"path": str(path), "branch": branch, "base": "HEAD", "note": "Original working tree was not changed."}

    def remove_clean(self, path: str) -> dict:
        target = self.resolve(path)
        if target == self.root:
            raise ValueError("Cannot remove primary worktree")
        status = _git(target, "status", "--porcelain", "--untracked-files=all")
        if status.strip():
            raise ValueError("Worktree has changes or untracked files; review them first")
        _git(self.root, "worktree", "remove", str(target), timeout=30)
        return {"removed": str(target), "note": "Git branch remains available."}
