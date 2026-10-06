#!/bin/bash
# Static structure tests for the installer modules (issue #683).
# Modules need root and absolute system paths, so ordering and error-handling
# invariants are asserted on the source instead of by running them.
#
# Usage: bash deploy/install/tests/test-module-structure.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SRC="$(cd "$TESTS_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# ─── Syntax of everything the installer executes ─────────────────────────────
for f in "$INSTALL_SRC"/install.sh "$INSTALL_SRC"/lib/*.sh "$INSTALL_SRC"/modules/*.sh; do
    if bash -n "$f" 2>/dev/null; then pass "syntax ok: ${f#"$INSTALL_SRC"/}"; else fail "syntax error: ${f#"$INSTALL_SRC"/}"; fi
done

# ─── Module 10: core (enable) before optional extras, no hard exit after ─────
M10="$INSTALL_SRC/modules/10-systemd-services.sh"
ENABLE_LINE=$(awk '/systemctl enable "\$service"/ {print NR; exit}' "$M10")
MARKER_LINE=$(awk '/^# --- Optional extras ---/ {print NR; exit}' "$M10")
FIRST_OPT_LINE=$(awk '/^run_optional / {print NR; exit}' "$M10")

if [[ -n "$ENABLE_LINE" && -n "$MARKER_LINE" && -n "$FIRST_OPT_LINE" ]]; then
    pass "module 10: enable loop, optional marker and run_optional calls found"
else
    fail "module 10: missing enable loop ($ENABLE_LINE), marker ($MARKER_LINE) or run_optional ($FIRST_OPT_LINE)"
fi
if [[ -n "$ENABLE_LINE" && -n "$MARKER_LINE" && "$ENABLE_LINE" -lt "$MARKER_LINE" && "$MARKER_LINE" -lt "${FIRST_OPT_LINE:-0}" ]]; then
    pass "module 10: systemctl enable runs before the optional extras"
else
    fail "module 10: optional extras are not strictly after systemctl enable"
fi
BAD_EXITS=$(awk -v m="${MARKER_LINE:-999999}" 'NR > m && /exit 1/ {print NR": "$0}' "$M10")
if [[ -z "$BAD_EXITS" ]]; then
    pass "module 10: no 'exit 1' after the optional marker"
else
    fail "module 10: hard exit in optional section: $BAD_EXITS"
fi

# ─── Results ─────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
