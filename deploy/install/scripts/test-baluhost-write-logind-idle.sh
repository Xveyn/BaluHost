#!/bin/bash
# Automated tests for baluhost-write-logind-idle. Runs in CI on
# ubuntu-latest; no real root needed because we override the config
# path and PATH-stub systemctl.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL="$SCRIPT_DIR/baluhost-write-logind-idle.sh"

if [[ ! -f "$ORIGINAL" ]]; then
    echo "FAIL: helper script not found at $ORIGINAL" >&2
    exit 1
fi

FAILS=0
PASSES=0

# Each case runs the helper with a patched copy that writes to /tmp.
prepare() {
    local conf="$1"
    HELPER="$(mktemp)"
    sed "s|/etc/systemd/logind.conf.d/baluhost-idle.conf|$conf|g" "$ORIGINAL" > "$HELPER"
    chmod +x "$HELPER"
    # Stub systemctl
    STUB_DIR="$(mktemp -d)"
    cat > "$STUB_DIR/systemctl" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$STUB_DIR/systemctl"
    export PATH="$STUB_DIR:$PATH"
}

cleanup() {
    rm -f "$HELPER" "$1"
    rm -rf "$STUB_DIR"
    # Restore PATH (CI restarts shell anyway)
}

assert_exit() {
    local name="$1"; shift
    local expected="$1"; shift
    "$@"
    local rc=$?
    if [[ $rc -eq $expected ]]; then
        echo "PASS: $name (exit=$rc)"
        PASSES=$((PASSES+1))
    else
        echo "FAIL: $name (expected exit=$expected, got $rc)"
        FAILS=$((FAILS+1))
    fi
}

# Case 1: no args
prepare "/tmp/h1.conf"
assert_exit "no-args" 2 bash "$HELPER"
cleanup "/tmp/h1.conf"

# Case 2: non-integer timeout
prepare "/tmp/h2.conf"
assert_exit "non-int-timeout" 2 bash "$HELPER" --timeout abc --action suspend
cleanup "/tmp/h2.conf"

# Case 3: too-small timeout
prepare "/tmp/h3.conf"
assert_exit "small-timeout" 2 bash "$HELPER" --timeout 30 --action suspend
cleanup "/tmp/h3.conf"

# Case 4: invalid action
prepare "/tmp/h4.conf"
assert_exit "bad-action" 2 bash "$HELPER" --timeout 900 --action poweroff
cleanup "/tmp/h4.conf"

# Case 5: happy path
prepare "/tmp/h5.conf"
assert_exit "happy-suspend" 0 bash "$HELPER" --timeout 900 --action suspend
if grep -q "IdleAction=suspend" /tmp/h5.conf && grep -q "IdleActionSec=900s" /tmp/h5.conf; then
    echo "PASS: happy-suspend file content"
    PASSES=$((PASSES+1))
else
    echo "FAIL: happy-suspend file content"
    cat /tmp/h5.conf
    FAILS=$((FAILS+1))
fi
cleanup "/tmp/h5.conf"

# Case 6: happy hibernate
prepare "/tmp/h6.conf"
assert_exit "happy-hibernate" 0 bash "$HELPER" --timeout 1800 --action hibernate
grep -q "IdleAction=hibernate" /tmp/h6.conf && grep -q "IdleActionSec=1800s" /tmp/h6.conf \
    && { echo "PASS: happy-hibernate file content"; PASSES=$((PASSES+1)); } \
    || { echo "FAIL: happy-hibernate file content"; FAILS=$((FAILS+1)); }
cleanup "/tmp/h6.conf"

echo
echo "Total: $PASSES passed, $FAILS failed"
[[ $FAILS -eq 0 ]]
