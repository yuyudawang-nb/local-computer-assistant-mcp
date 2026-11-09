#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python="$repo_dir/.venv/bin/python"
if [[ ! -x "$python" ]]; then
  printf 'Missing virtualenv. Run: uv sync --python 3.11\n' >&2
  exit 2
fi
# Never pass Tunnel/OpenAI/GitHub keys from the launcher to arbitrary MCP commands.
unset CONTROL_PLANE_API_KEY OPENAI_API_KEY OPENAI_ADMIN_KEY GITHUB_TOKEN GH_TOKEN
export LOCAL_RESEARCH_ROOT="${LOCAL_RESEARCH_ROOT:-$HOME}"
export LOCAL_RESEARCH_ALLOW_EXEC="${LOCAL_RESEARCH_ALLOW_EXEC:-0}"
export LOCAL_RESEARCH_ALLOW_DESKTOP="${LOCAL_RESEARCH_ALLOW_DESKTOP:-0}"
if [[ ! -d "$LOCAL_RESEARCH_ROOT" ]]; then
  printf 'LOCAL_RESEARCH_ROOT must point to an existing directory.\n' >&2
  exit 2
fi
exec "$python" "$repo_dir/server.py"
