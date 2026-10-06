#!/bin/bash
# Tests for lib/common.sh helpers used by the installer modules (issue #683):
# install_sudoers_file must be safe to call from an `if` condition (errexit is
# OFF there), so it has to propagate every failure itself.
#
# Usage: bash deploy/install/tests/test-install-helpers.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SRC="$(cd "$TESTS_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

source "$INSTALL_SRC/lib/common.sh"
set +e  # common.sh enables errexit; the assertions below must run to the end

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Fake visudo: exit code controlled by FAKE_VISUDO_RC.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/visudo" <<'EOT'
#!/bin/bash
[[ -z "${FAKE_VISUDO_MSG:-}" ]] || echo "$FAKE_VISUDO_MSG" >&2
exit "${FAKE_VISUDO_RC:-0}"
EOT
chmod +x "$TMP/bin/visudo"
PATH="$TMP/bin:$PATH"

TPL="$TMP/sudoers.tpl"
echo '@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/true' > "$TPL"

# 1. Success: rendered, mode 440, rc 0.
DEST="$TMP/ok-sudoers"
FAKE_VISUDO_RC=0 install_sudoers_file "$TPL" "$DEST" "BALUHOST_USER=baluhost" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 0 ]]; then pass "success returns 0"; else fail "success returned $RC"; fi
if [[ "$(stat -c %a "$DEST" 2>/dev/null)" == "440" ]]; then pass "file mode is 440"; else fail "file mode is not 440"; fi
if grep -q '^baluhost ALL=' "$DEST" 2>/dev/null; then pass "template rendered"; else fail "template not rendered"; fi

# 2. visudo rejects the file: rc 1, file removed.
DEST="$TMP/bad-sudoers"
FAKE_VISUDO_RC=1 install_sudoers_file "$TPL" "$DEST" "BALUHOST_USER=baluhost" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 1 ]]; then pass "visudo failure returns 1"; else fail "visudo failure returned $RC"; fi
if [[ ! -e "$DEST" ]]; then pass "rejected sudoers file removed"; else fail "rejected sudoers file left behind"; fi

# 3. Destination directory missing (the polkit/udev shape): rc 1, no 'Installed'.
OUT=$(if install_sudoers_file "$TPL" "$TMP/no-such-dir/sudoers" "BALUHOST_USER=baluhost"; then echo IF-TRUE; else echo IF-FALSE; fi 2>&1)
if grep -q 'IF-FALSE' <<<"$OUT"; then pass "missing dest dir fails in if-context"; else fail "missing dest dir did not fail: $OUT"; fi
if ! grep -q 'Installed sudoers rule' <<<"$OUT"; then
    pass "no false success message after a failed write"
else
    fail "reported success after a failed write (errexit trap): $OUT"
fi

# 4. Template missing: warn and skip with rc 0 (matches the old 'skipping' branch).
install_sudoers_file "$TMP/missing.tpl" "$TMP/never" "BALUHOST_USER=x" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 0 && ! -e "$TMP/never" ]]; then pass "missing template skipped with rc 0"; else fail "missing template: rc=$RC"; fi

# 5. process_template into a missing directory returns non-zero (documents the
# behavior the optional blocks rely on).
process_template "$TPL" "$TMP/no-such-dir/x" "BALUHOST_USER=x" >/dev/null 2>&1
RC=$?
if [[ $RC -ne 0 ]]; then pass "process_template fails for missing target dir"; else fail "process_template returned 0 for missing target dir"; fi

# 6. visudo's own error text must reach the operator (the file is deleted
# afterwards, so the message is the only diagnostic left).
OUT=$(FAKE_VISUDO_RC=1 FAKE_VISUDO_MSG="parse error in line 3" install_sudoers_file "$TPL" "$TMP/diag-sudoers" "BALUHOST_USER=baluhost" 2>&1)
if grep -q 'parse error in line 3' <<<"$OUT"; then
    pass "visudo error text is shown"
else
    fail "visudo error text lost: $OUT"
fi

# 7. run_optional records a failed step and never fails itself; the report
# lists it. An empty failure list reports nothing.
ok_step() { return 0; }
bad_step() { return 1; }
OPTIONAL_FAILURES=()
OUT=$(report_optional_failures 2>&1)
RC=$?
if [[ $RC -eq 0 && -z "$OUT" ]]; then pass "empty failure list reports nothing"; else fail "empty failure list: rc=$RC out='$OUT'"; fi
run_optional "good step" ok_step >/dev/null 2>&1
RC1=$?
run_optional "bad step" bad_step >/dev/null 2>&1
RC2=$?
if [[ $RC1 -eq 0 && $RC2 -eq 0 ]]; then pass "run_optional always returns 0"; else fail "run_optional returned $RC1/$RC2"; fi
if [[ ${#OPTIONAL_FAILURES[@]} -eq 1 && "${OPTIONAL_FAILURES[0]}" == "bad step" ]]; then
    pass "only the failed step is recorded"
else
    fail "recorded failures: ${OPTIONAL_FAILURES[*]:-<none>}"
fi
OUT=$(report_optional_failures 2>&1)
if grep -q 'bad step' <<<"$OUT" && grep -q 'NOT installed' <<<"$OUT"; then
    pass "report lists the failed step"
else
    fail "report missing failed step: $OUT"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
