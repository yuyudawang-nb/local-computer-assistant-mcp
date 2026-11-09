#!/usr/bin/env python3
"""Fail closed on unexpected release files, machine-specific data and likely credentials."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = set("""
.gitignore .env.example LICENSE README.md pyproject.toml uv.lock
server.py desktop.py editing.py managed_process_ctl.py managed_processes.py
processes.py project_state.py providers.py worktrees.py review_ui.html
run_mcp_for_chatgpt.sh start_chatgpt_tunnel.sh
scripts/check_public_release.py
docs/CHATGPT_TUNNEL.md docs/CODEX.md docs/SECURITY.md
tests/smoke_desktop_mcp.py tests/smoke_mcp.py tests/smoke_project_mcp.py
tests/test_editing_desktop.py tests/test_managed_mcp.py
tests/test_managed_processes.py tests/test_project_workspace.py tests/test_server.py
tests/test_public_release.py
""".split())
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BAD_PATTERNS = [
    ("personal home directory", re.compile(r"/home/(?!user/|YOUR_USER/)[A-Za-z0-9_-]{2,}/")),
    ("credential-bearing SSH file", re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:github_pat_|gh[pousr]_)[a-zA-Z0-9_]{20,}")),
    ("secret API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("non-example email address", re.compile(r"\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("private IPv4 address", re.compile(r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b")),
    ("local machine proxy port", re.compile(r"127\.0\.0\.1:(?!8080\b)\d{3,5}\b")),
    ("concrete tunnel id", re.compile(r"\btunnel_(?!YOUR_)[A-Za-z0-9_-]{18,}\b")),
]
errors = []
seen = set()
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
    for name in files:
        path = Path(base) / name
        rel = path.relative_to(ROOT).as_posix()
        if rel not in ALLOWED:
            errors.append(f"unexpected file: {rel}")
            continue
        seen.add(rel)
        if path.is_symlink():
            errors.append(f"symlink not permitted: {rel}")
            continue
        try:
            data = path.read_bytes()
            if len(data) > 500_000 or b"\x00" in data:
                errors.append(f"not a small plain-text file: {rel}")
                continue
            text = data.decode("utf-8")
        except (OSError, UnicodeError):
            errors.append(f"could not read text: {rel}")
            continue
        for label, pattern in BAD_PATTERNS:
            matches = [m.group(0) for m in pattern.finditer(text)]
            if label == "non-example email address":
                matches = [v for v in matches if not v.lower().endswith(
                    ("@example.com", "@example.org", "@example.net", "@example.invalid"))]
            if matches:
                errors.append(f"{rel}: {label}")
missing = ALLOWED - seen
for rel in sorted(missing):
    errors.append(f"expected file missing: {rel}")
if errors:
    print("PUBLIC RELEASE CHECK FAILED:")
    print("\n".join("- " + x for x in errors))
    sys.exit(1)
print(f"PUBLIC RELEASE CHECK PASSED: {len(seen)} allowlisted UTF-8 files, no flagged personal paths or credential patterns")
