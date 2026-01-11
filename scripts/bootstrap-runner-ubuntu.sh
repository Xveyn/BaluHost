#!/usr/bin/env bash
set -euo pipefail

# bootstrap-runner-ubuntu.sh
# Provision an Ubuntu VM for use as a self-hosted GitHub Actions runner
# with mdadm available and optional loop devices for safe RAID testing.
#
# Usage (run as root or via sudo):
#   ./bootstrap-runner-ubuntu.sh \
#     --repo https://github.com/OWNER/REPO \
#     --token YOUR_RUNNER_TOKEN \
#     --labels "self-hosted,linux,mdadm" \
#     --runner-user runner \
#     --workdir /opt/actions-runner \
#     --loop-devices 3
#
# Notes:
# - You must provide a runner registration token from GitHub (Settings -> Actions -> Runners -> New self-hosted runner).
# - The script will create the specified number of loop devices (safest for ephemeral VMs).
# - It will add a sudoers entry allowing the runner user to run mdadm/losetup without password.
# - Adjust paths, user names, and labels as needed.

usage() {
  grep '^#' "$0" | sed -e 's/^#//'
}

# Default values
REPO_URL=""
RUNNER_TOKEN=""
LABELS="self-hosted,linux,mdadm"
RUNNER_USER="runner"
WORK_DIR="/opt/actions-runner"
LOOP_DEVICES=3
CREATE_RUNNER_USER=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_URL="$2"; shift 2;;
    --token) RUNNER_TOKEN="$2"; shift 2;;
    --labels) LABELS="$2"; shift 2;;
    --runner-user) RUNNER_USER="$2"; shift 2;;
    --workdir) WORK_DIR="$2"; shift 2;;
    --loop-devices) LOOP_DEVICES="$2"; shift 2;;
    --no-create-user) CREATE_RUNNER_USER=false; shift 1;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [[ -z "$REPO_URL" || -z "$RUNNER_TOKEN" ]]; then
  echo "ERROR: --repo and --token are required"
  usage
  exit 2
fi

apt-get update
apt-get install -y --no-install-recommends \
  curl jq tar gzip ca-certificates mdadm util-linux sudo procps

# Create runner user if requested
if $CREATE_RUNNER_USER; then
  if id -u "$RUNNER_USER" >/dev/null 2>&1; then
    echo "User $RUNNER_USER already exists"
  else
    useradd --create-home --shell /bin/bash "$RUNNER_USER"
    echo "Created user $RUNNER_USER"
  fi
fi

# Ensure workdir
mkdir -p "$WORK_DIR"
chown "$RUNNER_USER":"$RUNNER_USER" "$WORK_DIR"

# Download latest GitHub Actions Runner
echo "Fetching latest Actions Runner release..."
API_JSON=$(curl -sS https://api.github.com/repos/actions/runner/releases/latest)
ASSET_URL=$(echo "$API_JSON" | jq -r '.assets[] | select(.name | test("actions-runner-linux-x64.*tar.gz")) | .browser_download_url')
if [[ -z "$ASSET_URL" || "$ASSET_URL" == "null" ]]; then
  echo "Failed to find runner asset URL" >&2
  exit 1
fi

echo "Downloading runner from $ASSET_URL"
RUNNER_TARBALL="$WORK_DIR/runner.tar.gz"
curl -sSL "$ASSET_URL" -o "$RUNNER_TARBALL"

# Extract as runner user
tar -xzf "$RUNNER_TARBALL" -C "$WORK_DIR"
chown -R "$RUNNER_USER":"$RUNNER_USER" "$WORK_DIR"
rm -f "$RUNNER_TARBALL"

# Add sudoers entry for runner user to run mdadm/losetup without password
SUDOERS_FILE="/etc/sudoers.d/github-runner-mdadm"
cat > "$SUDOERS_FILE" <<EOF
# Allow the runner user to manage loop devices and mdadm for test workloads
$RUNNER_USER ALL=(ALL) NOPASSWD: /sbin/mdadm, /sbin/losetup, /usr/bin/losetup, /sbin/losetup -f, /bin/losetup
EOF
chmod 0440 "$SUDOERS_FILE"

# Create loop devices (files + losetup) as non-root runner operations may need sudo
echo "Creating $LOOP_DEVICES loop devices (for RAID tests)..."
LOOP_DIR="/var/lib/raid-test-disks"
mkdir -p "$LOOP_DIR"
chown "$RUNNER_USER":"$RUNNER_USER" "$LOOP_DIR"

for i in $(seq 1 "$LOOP_DEVICES"); do
  IMG="$LOOP_DIR/raid-disk-$i.img"
  if [[ ! -f "$IMG" ]]; then
    echo "Creating $IMG (100M)"
    fallocate -l 100M "$IMG"
    chown "$RUNNER_USER":"$RUNNER_USER" "$IMG"
  else
    echo "$IMG exists, skipping creation"
  fi
  # attach to loop device
  sudo losetup -fP "$IMG" || true
done

# Register the runner (interactive configuration)
# Note: runner configuration persists and the service can be installed to run on boot.
cd "$WORK_DIR"
RUNNER_SCRIPT="./config.sh"

if [[ ! -x "$RUNNER_SCRIPT" ]]; then
  echo "Runner config script missing or not executable: $RUNNER_SCRIPT"
  ls -la
  exit 1
fi

echo "Configuring GitHub Actions runner (non-interactive)..."
# Build the registration command
./config.sh --unattended --url "$REPO_URL" --token "$RUNNER_TOKEN" --labels "$LABELS" --work "$WORK_DIR"

# Install and start service as runner user
./svc.sh install
./svc.sh start

cat <<EOF
Bootstrap complete.
- Runner installed at: $WORK_DIR
- Loop devices stored under: $LOOP_DIR
- Sudoers entry created: $SUDOERS_FILE

Cleanup notes:
- To remove loop devices: sudo losetup -a  # list, then sudo losetup -d /dev/loopX
- To unregister runner: run "$WORK_DIR/config.sh remove --unattended --token <token>"

Security notes:
- This machine should be a dedicated test VM. Avoid running tests on multi-tenant or production hosts.
EOF
