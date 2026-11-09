"""Workspace-scoped patch application and Git review for the local MCP."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _inside(root: Path, relative: str) -> Path:
    if not relative or relative.startswith("-") or "\\" in relative:
        raise ValueError("Expected a relative workspace path")
    path = Path(relative)
    if path.is_absolute() or any(part in (".", "..", ".git") for part in path.parts):
        raise ValueError("Patch path must stay inside the workspace")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Patch path resolves outside the workspace")
    return resolved


def _patch_paths(root: Path, patch: str) -> list[str]:
    if not patch or len(patch.encode("utf-8")) > 100_000 or "\x00" in patch:
        raise ValueError("Patch must be nonempty UTF-8 text under 100 KB")
    paths = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/([^\s]+) b/([^\s]+)", line)
            if not match or match.group(1) != match.group(2):
                raise ValueError("Use ordinary git diff format for one unchanged path per file")
            paths.append(match.group(1))
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ",
                              "GIT binary patch", "Binary files ", "old mode ", "new mode ",
                              "deleted file mode ")):
            raise ValueError("Only text edits and new text files are supported")
        elif line.startswith(("--- ", "+++ ")):
            header = line[4:]
            if header != "/dev/null":
                prefix = "a/" if line.startswith("--- ") else "b/"
                if not header.startswith(prefix) or header[2:] not in paths:
                    raise ValueError("Patch file header does not match its diff header")
    if not paths:
        raise ValueError("Expected at least one 'diff --git' header")
    for path in paths:
        _inside(root, path)
    return paths


def apply_patch(root: Path, patch: str) -> dict:
    """Apply a conventional git unified diff after path and applicability checks."""
    paths = _patch_paths(root, patch)
    data = patch.encode("utf-8")
    base = ["git", "-C", str(root), "apply"]
    check = subprocess.run(base + ["--check", "-"], input=data, capture_output=True, timeout=15)
    if check.returncode:
        return {"applied": False, "paths": paths,
                "error": check.stderr.decode("utf-8", "replace")[:4000]}
    result = subprocess.run(base + ["-"], input=data, capture_output=True, timeout=15)
    return {"applied": result.returncode == 0, "paths": paths,
            "error": result.stderr.decode("utf-8", "replace")[:4000] if result.returncode else ""}


def git_review(root: Path, relative_path: str = "", max_chars: int = 40_000) -> dict:
    """Return tracked changes, staged changes, whitespace errors, and status."""
    root = root.resolve()
    pathspec = []
    if relative_path:
        target = _inside(root, relative_path)
        pathspec = ["--", str(target.relative_to(root))]
    max_chars = max(100, min(int(max_chars), 100_000))

    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(root), *args, *pathspec],
                                capture_output=True, text=True, errors="replace", timeout=15)
        if result.returncode not in (0, 1, 2) or (result.returncode != 0 and args[0] != "diff"):
            raise RuntimeError(result.stderr[:2000] or "Git command failed")
        return result.stdout[:max_chars]

    return {"root": str(root), "path": relative_path or ".",
            "status": git("status", "--short"),
            "unstaged_diff": git("diff", "--no-ext-diff", "--no-color"),
            "staged_diff": git("diff", "--cached", "--no-ext-diff", "--no-color"),
            "whitespace_errors": git("diff", "--check"),
            "note": "Git diff excludes untracked file contents; status still lists them."}
