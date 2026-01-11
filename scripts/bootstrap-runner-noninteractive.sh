#!/usr/bin/env bash
set -euo pipefail

# Non-interactive wrapper for bootstrap-runner-ubuntu.sh
# Reads configuration from environment variables and runs the bootstrap script.

# Required env vars:
# - BOOTSTRAP_REPO_URL
# - BOOTSTRAP_RUNNER_TOKEN

: "${BOOTSTRAP_REPO_URL:?Missing BOOTSTRAP_REPO_URL}"
: "${BOOTSTRAP_RUNNER_TOKEN:?Missing BOOTSTRAP_RUNNER_TOKEN}"

LABELS="${BOOTSTRAP_LABELS:-self-hosted,linux,mdadm}"
RUNNER_USER="${BOOTSTRAP_RUNNER_USER:-runner}"
WORK_DIR="${BOOTSTRAP_WORK_DIR:-/opt/actions-runner}"
LOOP_DEVICES="${BOOTSTRAP_LOOP_DEVICES:-3}"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/bootstrap-runner-ubuntu.sh"

if [[ ! -x "$BOOTSTRAP_SCRIPT" ]]; then
  echo "Bootstrap script not found or not executable: $BOOTSTRAP_SCRIPT"
  exit 1
fi

sudo "$BOOTSTRAP_SCRIPT" \
  --repo "$BOOTSTRAP_REPO_URL" \
  --token "$BOOTSTRAP_RUNNER_TOKEN" \
  --labels "$LABELS" \
  --runner-user "$RUNNER_USER" \
  --workdir "$WORK_DIR" \
  --loop-devices "$LOOP_DEVICES"
