#!/usr/bin/env bash
# Build a .deb wrapping the standalone baluhost-tui PyInstaller binary.
#
# Usage: build_deb.sh <version> <binary_path> [out_dir]
#   <version>      Debian package version, e.g. 1.36.0 or 0.0.0+abc1234
#   <binary_path>  Path to the PyInstaller one-file binary
#   [out_dir]      Output directory for the .deb (default: dist)
set -euo pipefail

VERSION="${1:?version required}"
BIN="${2:?binary path required}"
OUT="${3:-dist}"

if [[ ! -f "${BIN}" ]]; then
  echo "error: binary not found: ${BIN}" >&2
  exit 1
fi

PKG="baluhost-tui_${VERSION}_amd64"
WORK="$(mktemp -d)"
STAGE="${WORK}/${PKG}"
mkdir -p "${STAGE}/DEBIAN" "${STAGE}/usr/bin"
install -m 0755 "${BIN}" "${STAGE}/usr/bin/baluhost-tui"

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: baluhost-tui
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: amd64
Maintainer: Xveyn <noreply@users.noreply.github.com>
Description: BaluHost TUI - terminal admin/recovery companion
 Standalone terminal UI for administering a BaluHost NAS over the local
 Unix socket (channel=local). Self-contained: bundles its own Python
 runtime, so no system Python is required. Linux x86_64 only.
EOF

mkdir -p "${OUT}"
dpkg-deb --build --root-owner-group "${STAGE}" "${OUT}/${PKG}.deb"
rm -rf "${WORK}"
echo "built ${OUT}/${PKG}.deb"
