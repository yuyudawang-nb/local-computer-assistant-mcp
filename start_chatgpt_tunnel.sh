#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
server="$repo_dir/run_mcp_for_chatgpt.sh"
profile="${LOCAL_MCP_TUNNEL_PROFILE:-local-computer-assistant}"
tunnel_id="${1:-}"
key_dir="${XDG_CONFIG_HOME:-$HOME/.config}/local-computer-assistant-mcp"
key_file="$key_dir/tunnel-runtime.key"
save_key_after_preflight=0
client="${TUNNEL_CLIENT:-}"
if [[ -z "$client" ]]; then client="$(command -v tunnel-client || true)"; fi
if [[ -z "$client" || ! -x "$client" ]]; then
  printf 'Install official tunnel-client and put it on PATH (or set TUNNEL_CLIENT=/absolute/path).\n' >&2
  exit 2
fi
if [[ ! $tunnel_id =~ ^tunnel_[A-Za-z0-9_-]{8,}$ ]]; then
  printf 'Usage: %s tunnel_ID (create your OWN tunnel in OpenAI Platform)\n' "$0" >&2
  exit 2
fi
if [[ ! -x "$server" ]]; then
  printf 'Make launcher executable: chmod +x run_mcp_for_chatgpt.sh\n' >&2
  exit 2
fi
if [[ -L "$key_dir" || -L "$key_file" ]]; then
  printf 'Refusing a symlinked runtime-key path.\n' >&2
  exit 2
fi
if [[ "${LOCAL_RESEARCH_REKEY:-0}" == 1 ]]; then unset CONTROL_PLANE_API_KEY; fi
if [[ -z "${CONTROL_PLANE_API_KEY:-}" && -f "$key_file" && "${LOCAL_RESEARCH_REKEY:-0}" != 1 ]]; then
  if [[ "$(stat -c %u "$key_file")" != "$(id -u)" ]]; then
    printf 'Runtime key file belongs to a different user.\n' >&2
    exit 2
  fi
  chmod 600 "$key_file"
  CONTROL_PLANE_API_KEY="$(cat "$key_file")"
  export CONTROL_PLANE_API_KEY
fi
if [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
  if [[ ! -t 0 ]]; then
    printf 'Run in a terminal to enter your key privately.\n' >&2
    exit 2
  fi
  read -r -s -p 'Your restricted OpenAI Platform tunnel runtime key: ' CONTROL_PLANE_API_KEY
  printf '\n' >&2
  if [[ -z "$CONTROL_PLANE_API_KEY" ]]; then
    printf 'Key cannot be empty.\n' >&2
    exit 2
  fi
  export CONTROL_PLANE_API_KEY
  save_key_after_preflight=1
fi

# Respect the user's proxy settings. No public server and no inbound port.
if ! env -u OPENAI_ADMIN_KEY "$client" admin tunnels get "$tunnel_id" >/dev/null; then
  printf 'Tunnel access failed: check tunnel ID, organization and Tunnels Read + Use.\n' >&2
  exit 1
fi
if [[ "$save_key_after_preflight" == 1 ]]; then
  umask 077
  mkdir -p "$key_dir"
  chmod 700 "$key_dir"
  printf '%s' "$CONTROL_PLANE_API_KEY" > "$key_file"
  chmod 600 "$key_file"
fi
"$client" init --sample sample_mcp_stdio_local --profile "$profile" --tunnel-id "$tunnel_id" --mcp-command "$server" --health-listen-addr 127.0.0.1:8080 --force
"$client" doctor --profile "$profile" --explain
printf 'Tunnel connected. Keep this terminal open to use this computer from ChatGPT.\n' >&2
exec "$client" run --profile "$profile"
