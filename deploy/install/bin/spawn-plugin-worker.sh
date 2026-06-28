#!/bin/bash
# BaluHost plugin sandbox — hardened worker spawn wrapper.
#
# Invoked ONLY by the baluhost service user via a scoped sudoers entry:
#   baluhost ALL=(root) NOPASSWD: /opt/baluhost/deploy/bin/spawn-plugin-worker.sh
#
# Validates the caller-influenced flags, then drops privilege and isolates:
#   prlimit (limits, root) -> unshare --net (netns, root) ->
#   setpriv --reuid baluhost-plugin (drop) -> venv python -m worker
#
# Trusted constants below are NEVER taken from the caller.
set -euo pipefail

EXTERNAL_DIR="/var/lib/baluhost/plugins"
PLUGIN_USER="baluhost-plugin"
VENV_PYTHON="/opt/baluhost/backend/.venv/bin/python"
WORKER_MODULE="app.plugins.sandbox.worker"

# rlimits: CPU seconds, max processes, address space (bytes), max file size (bytes).
RL_CPU=60
RL_NPROC=64
RL_AS=536870912     # 512 MiB
RL_FSIZE=67108864   # 64 MiB

connect=""
plugin_dir=""
plugin_name=""

# Parse only the flags we use; ignore everything else (python, -m, module name).
while [[ $# -gt 0 ]]; do
  case "$1" in
    --connect)     connect="${2:-}";     shift 2 ;;
    --plugin-dir)  plugin_dir="${2:-}";  shift 2 ;;
    --plugin-name) plugin_name="${2:-}"; shift 2 ;;
    *)             shift ;;
  esac
done

# 1) plugin-name: strict allowlist.
[[ "$plugin_name" =~ ^[a-z0-9_]+$ ]] || { echo "bad plugin-name" >&2; exit 64; }

# 2) connect: UDS path or host:port, no shell metacharacters.
[[ "$connect" =~ ^[A-Za-z0-9_./:@-]+$ ]] || { echo "bad connect" >&2; exit 67; }

# 3) plugin-dir: must resolve, and canonicalize to exactly <EXTERNAL_DIR>/<name>.
real_dir="$(realpath -e -- "$plugin_dir" 2>/dev/null)" || { echo "dir not resolvable" >&2; exit 65; }
[[ "$real_dir" == "$EXTERNAL_DIR/$plugin_name" ]] || { echo "dir outside jail" >&2; exit 66; }

exec prlimit \
    "--cpu=$RL_CPU" "--nproc=$RL_NPROC" "--as=$RL_AS" "--fsize=$RL_FSIZE" -- \
  unshare --net -- \
  setpriv --reuid "$PLUGIN_USER" --regid "$PLUGIN_USER" --init-groups --no-new-privs -- \
    "$VENV_PYTHON" -m "$WORKER_MODULE" \
       --connect "$connect" --plugin-dir "$real_dir" --plugin-name "$plugin_name"
