#!/usr/bin/env bash
# bootstrap-ci-runner.sh
#
# Provision the BaluHost CI sandbox runner on the NAS.
#
# - Creates an unprivileged 'ci-runner' Linux user (no sudo, no production read access).
# - Installs Podman and rootless prerequisites.
# - Configures subuid/subgid + systemd lingering for rootless containers.
# - Installs and registers a GitHub Actions self-hosted runner instance as 'ci-runner'
#   with labels: self-hosted,Linux,X64,ci-sandbox.
# - Pre-pulls docker.io/library/python:3.11-slim and docker.io/library/node:20-slim
#   into ci-runner's storage.
# - Runs self-tests; aborts with a clear error if any isolation guarantee is violated.
#
# Idempotent: safe to re-run.
#
# Usage:
#   sudo ./bootstrap-ci-runner.sh --token <RUNNER_REGISTRATION_TOKEN>
#   # second instance (parallel CI jobs; frontend-build + backend-tests):
#   sudo ./bootstrap-ci-runner.sh --token <TOKEN> --name BaluNode-ci-sandbox-2 --dir runner-2
#
# Get the token from: https://github.com/Xveyn/BaluHost/settings/actions/runners/new
# (Click "New self-hosted runner", copy the value passed to --token in the displayed
# config.sh command. Token is single-use, expires in ~1 hour.)
#
# Reference: docs/superpowers/specs/2026-05-19-self-hosted-backend-tests-design.md

set -euo pipefail

# ---------- Configuration ----------
RUNNER_USER="ci-runner"
RUNNER_HOME="/var/lib/ci-runner"
RUNNER_DIR_NAME="runner"   # unique per instance; second instance: --dir runner-2
REPO_URL="https://github.com/Xveyn/BaluHost"
RUNNER_LABELS="self-hosted,Linux,X64,ci-sandbox"
RUNNER_NAME="${RUNNER_NAME:-BaluNode-ci-sandbox}"
TEST_IMAGE="docker.io/library/python:3.11-slim"
NODE_IMAGE="docker.io/library/node:20-slim"
SUBUID_RANGE="100000-165535"
SUBGID_RANGE="100000-165535"

# ---------- Arg parsing ----------
RUNNER_TOKEN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) RUNNER_TOKEN="$2"; shift 2 ;;
    --name)  RUNNER_NAME="$2";  shift 2 ;;
    --dir)   RUNNER_DIR_NAME="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# RUNNER_DIR is per-instance via --dir.
RUNNER_DIR="${RUNNER_HOME}/${RUNNER_DIR_NAME}"

# RUNNER_WORK is NOT what config.sh actually uses for the runner's work directory
# (that's `--work "_work"` in Step 5, relative to $RUNNER_DIR — already per-instance
# for free once RUNNER_DIR is). This variable only seeds the legacy `mkdir -p` below;
# kept at its single pre-existing value for all instances.
RUNNER_WORK="${RUNNER_HOME}/_work"

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must be run as root (sudo)." >&2
  exit 1
fi

if [[ -z "$RUNNER_TOKEN" ]]; then
  echo "ERROR: --token is required. Get one from $REPO_URL/settings/actions/runners/new" >&2
  exit 2
fi

log() { echo "[bootstrap-ci-runner] $*"; }
as_runner() { sudo -u "$RUNNER_USER" -H "$@"; }

# ---------- Step 1: install packages ----------
log "Installing system packages (podman, uidmap, passt, slirp4netns, fuse-overlayfs, dbus-user-session)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  podman uidmap passt slirp4netns fuse-overlayfs dbus-user-session \
  curl tar ca-certificates jq

# ---------- Step 2: create ci-runner user ----------
if id -u "$RUNNER_USER" >/dev/null 2>&1; then
  log "User '$RUNNER_USER' already exists; reusing."
else
  log "Creating user '$RUNNER_USER' with home '$RUNNER_HOME'..."
  useradd --system --create-home --home-dir "$RUNNER_HOME" \
          --shell /bin/bash "$RUNNER_USER"
fi

# Defensive: ensure NOT in docker/sudo/baluhost groups (even if added previously).
for grp in docker sudo wheel baluhost; do
  if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx "$grp"; then
    log "Removing '$RUNNER_USER' from group '$grp' (isolation requirement)."
    gpasswd -d "$RUNNER_USER" "$grp"
  fi
done

mkdir -p "$RUNNER_WORK"
chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME"
chmod 0750 "$RUNNER_HOME"

# ---------- Step 3: subuid/subgid ----------
log "Configuring subuid/subgid (range $SUBUID_RANGE)..."
if ! grep -q "^${RUNNER_USER}:" /etc/subuid; then
  usermod --add-subuids "$SUBUID_RANGE" "$RUNNER_USER"
fi
if ! grep -q "^${RUNNER_USER}:" /etc/subgid; then
  usermod --add-subgids "$SUBGID_RANGE" "$RUNNER_USER"
fi

# ---------- Step 4: systemd lingering ----------
log "Enabling systemd lingering for '$RUNNER_USER'..."
loginctl enable-linger "$RUNNER_USER"

# Reconcile rootless Podman state now that the user manager + /run/user/<uid> are
# persistent. `loginctl enable-linger` (above) is the DURABLE fix — it keeps the
# pause process alive across logout/reboot — but it does not retroactively repair
# state that already went stale (e.g. from an earlier non-lingered session, which is
# why #127 recurred even though linger was already in this script). A one-time
# `podman system migrate` reconciles that stale pause.pid so the first `podman run`
# does not hit 'invalid internal status ... could not find any running process'.
# (migrate alone is only a temporary fix — linger is what makes it survive reboots.)
# Best-effort here; the linger + `podman info` self-tests below are the gate.
log "Reconciling rootless Podman state ('podman system migrate')..."
as_runner bash -lc 'podman system migrate' || true

# ---------- Step 5: GitHub Actions runner agent ----------
if [[ -x "$RUNNER_DIR/config.sh" ]] && [[ -f "$RUNNER_DIR/.runner" ]]; then
  log "Runner agent already installed; skipping download. Re-registration follows."
else
  log "Downloading latest GitHub Actions Runner..."
  install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$RUNNER_DIR"
  ASSET_URL=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
              | jq -r '.assets[] | select(.name | test("actions-runner-linux-x64.*\\.tar\\.gz$")) | .browser_download_url')
  if [[ -z "$ASSET_URL" || "$ASSET_URL" == "null" ]]; then
    echo "ERROR: could not resolve latest runner asset URL." >&2
    exit 1
  fi
  log "Fetching $ASSET_URL"
  as_runner curl -fsSL "$ASSET_URL" -o "$RUNNER_DIR/runner.tar.gz"
  as_runner tar -xzf "$RUNNER_DIR/runner.tar.gz" -C "$RUNNER_DIR"
  as_runner rm "$RUNNER_DIR/runner.tar.gz"
fi

# (Re-)register against the repo. If a previous registration exists, remove it first.
# Token passed via argv (not inside bash -c) — avoids shell-quoting issues if the
# token ever contains a single quote.
if [[ -f "$RUNNER_DIR/.runner" ]]; then
  log "Removing previous runner registration (best-effort)..."
  ( cd "$RUNNER_DIR" && as_runner ./config.sh remove --unattended --token "$RUNNER_TOKEN" ) || true
fi

log "Registering runner '$RUNNER_NAME' with labels '$RUNNER_LABELS'..."
( cd "$RUNNER_DIR" && as_runner ./config.sh --unattended \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --work "_work" \
    --replace )

# Install + start the systemd service for the runner. svc.sh requires root because
# it writes a unit file under /etc/systemd/system; the unit itself runs as ci-runner.
SVC_NAME="actions.runner.Xveyn-BaluHost.${RUNNER_NAME}.service"
if [[ -f "/etc/systemd/system/${SVC_NAME}" ]]; then
  log "Runner systemd service already installed; skipping install."
else
  log "Installing runner systemd service..."
  ( cd "$RUNNER_DIR" && ./svc.sh install "$RUNNER_USER" )
fi
log "Starting runner service (idempotent)..."
( cd "$RUNNER_DIR" && ./svc.sh start )

# ---------- Step 6: pre-pull test image ----------
log "Pre-pulling $TEST_IMAGE as $RUNNER_USER (first pull, ~50 MB)..."
as_runner podman pull "$TEST_IMAGE"
log "Pre-pulling $NODE_IMAGE as $RUNNER_USER..."
as_runner podman pull "$NODE_IMAGE"

# ---------- Step 7: self-tests ----------
log "Running isolation self-tests..."

fail() { echo "::error::SELF-TEST FAILED: $*" >&2; exit 1; }

# 7a: ci-runner cannot read .env.production (POSIX layer A).
if as_runner cat /opt/baluhost/.env.production >/dev/null 2>&1; then
  fail "ci-runner can read /opt/baluhost/.env.production — POSIX isolation broken."
fi
log "  [OK] ci-runner cannot read /opt/baluhost/.env.production"

# 7b: ci-runner has no sudo.
if as_runner sudo -n true >/dev/null 2>&1; then
  fail "ci-runner has passwordless sudo — must not."
fi
log "  [OK] ci-runner has no sudo"

# 7c: ci-runner not in docker/sudo/wheel groups.
RUNNER_GROUPS=$(id -nG "$RUNNER_USER")
for grp in docker sudo wheel; do
  if echo "$RUNNER_GROUPS" | tr ' ' '\n' | grep -qx "$grp"; then
    fail "ci-runner is in group '$grp' — must not be."
  fi
done
log "  [OK] ci-runner not in docker/sudo/wheel groups (current: $RUNNER_GROUPS)"

# Podman base health (issue #127): linger must be active and `podman info` must
# succeed — catches the stale rootless pause-process failure before any container
# actually runs (clearer diagnostic than a failing `podman run`).
if [[ "$(loginctl show-user "$RUNNER_USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
  fail "systemd linger is not enabled for $RUNNER_USER — rootless pause process will die on idle/reboot (issue #127). Run: loginctl enable-linger $RUNNER_USER"
fi
log "  [OK] systemd linger enabled for $RUNNER_USER"

if ! as_runner bash -lc 'podman info >/dev/null 2>&1'; then
  fail "rootless 'podman info' failed for $RUNNER_USER — stale pause process? Run: sudo -u $RUNNER_USER -H bash -lc 'podman system migrate'"
fi
log "  [OK] rootless 'podman info' healthy"

# 7d: rootless podman works.
HELLO_OUT=$(as_runner podman run --rm docker.io/library/hello-world 2>&1 || true)
if ! echo "$HELLO_OUT" | grep -q "Hello from Docker"; then
  fail "rootless podman hello-world failed. Output:
$HELLO_OUT"
fi
log "  [OK] rootless podman runs hello-world as $RUNNER_USER"

# 7e: container cannot see /opt/baluhost (no bind-mount).
# Use exit-code, not stderr parsing, to avoid locale issues.
if as_runner podman run --rm "$TEST_IMAGE" sh -c 'ls /opt/baluhost >/dev/null 2>&1'; then
  fail "container could enumerate /opt/baluhost — should be invisible."
fi
log "  [OK] container cannot see /opt/baluhost"

# 7f: GitHub Actions runner service is active.
if ! systemctl is-active --quiet "$SVC_NAME"; then
  fail "runner service '$SVC_NAME' is not active. Check: systemctl status $SVC_NAME"
fi
log "  [OK] $SVC_NAME is active"

log "All self-tests passed. Runner '$RUNNER_NAME' is online."
log "Verify via: gh api repos/Xveyn/BaluHost/actions/runners"
