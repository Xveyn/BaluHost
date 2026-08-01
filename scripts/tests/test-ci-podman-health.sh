#!/usr/bin/env bash
#
# Exercise scripts/ci-podman-health.sh against a fake podman.
#
# The script's whole job is to behave well when podman misbehaves, and that is
# not observable on the runner without breaking CI on purpose. A stub on PATH
# reproduces every branch in a second:
#
#   healthy            -> no repair at all
#   unhealthy, busy    -> waits, never migrates (this is #498: migrating here
#                         stops the other job's container and can crash)
#   unhealthy, idle    -> migrates, then reports healthy
#   migrate crashes    -> job still passes, warning only
#
# Run:  bash scripts/tests/test-ci-podman-health.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TARGET="${SCRIPT_DIR}/ci-podman-health.sh"

failures=0

# Builds a stub podman whose behaviour is driven by files in the sandbox:
#   info_fails_times : how many `podman info` calls report unhealthy
#   ps_output        : what `podman ps -q` prints
#   migrate_exit     : exit code of `podman system migrate`
make_sandbox() {
    local dir="$1" info_fails="$2" ps_output="$3" migrate_exit="$4"
    mkdir -p "${dir}/bin"
    echo "${info_fails}" > "${dir}/info_fails_times"
    printf '%s' "${ps_output}" > "${dir}/ps_output"
    echo "${migrate_exit}" > "${dir}/migrate_exit"
    : > "${dir}/calls"

    cat > "${dir}/bin/podman" <<'STUB'
#!/usr/bin/env bash
sandbox="$(dirname "$(dirname "$0")")"
echo "$*" >> "${sandbox}/calls"
case "$1 ${2:-}" in
  "info ")
    remaining="$(cat "${sandbox}/info_fails_times")"
    if [ "${remaining}" -gt 0 ]; then
      echo "$((remaining - 1))" > "${sandbox}/info_fails_times"
      echo "invalid internal status" >&2
      exit 125
    fi
    exit 0
    ;;
  "ps -q") cat "${sandbox}/ps_output" ;;
  "system migrate")
    code="$(cat "${sandbox}/migrate_exit")"
    [ "${code}" -ne 0 ] && echo "panic: runtime error: invalid memory address" >&2
    exit "${code}"
    ;;
esac
exit 0
STUB
    chmod +x "${dir}/bin/podman"

    # pgrep must not find a real conmon on the developer's machine, and must be
    # able to *pretend* to find one - the stub answers from a file.
    cat > "${dir}/bin/pgrep" <<'STUB'
#!/usr/bin/env bash
sandbox="$(dirname "$(dirname "$0")")"
[ -f "${sandbox}/conmon_running" ] && exit 0
exit 1
STUB
    chmod +x "${dir}/bin/pgrep"
}

run_target() {
    local dir="$1"
    PATH="${dir}/bin:${PATH}" \
    PODMAN_HEALTH_MAX_ATTEMPTS=3 \
    PODMAN_HEALTH_BUSY_WAIT=0 \
    PODMAN_HEALTH_SETTLE=0 \
        bash "${TARGET}" 2>&1
}

check() {
    local label="$1" condition="$2"
    if [ "${condition}" = "ok" ]; then
        echo "  PASS  ${label}"
    else
        echo "  FAIL  ${label}"
        failures=$((failures + 1))
    fi
}

# ---------------------------------------------------------------- healthy ---
echo "case: podman is healthy"
sandbox="$(mktemp -d)"
make_sandbox "${sandbox}" 0 "" 0
output="$(run_target "${sandbox}")"
status=$?
check "exits 0" "$([ ${status} -eq 0 ] && echo ok)"
check "does not migrate" "$(grep -q 'system migrate' "${sandbox}/calls" && echo no || echo ok)"
check "says healthy" "$(echo "${output}" | grep -q 'healthy' && echo ok)"
rm -rf "${sandbox}"

# ------------------------------------------------- unhealthy but busy (#498) ---
echo "case: unhealthy while another job has a container running"
sandbox="$(mktemp -d)"
make_sandbox "${sandbox}" 99 "abc123" 0
: > "${sandbox}/conmon_running"
output="$(run_target "${sandbox}")"
status=$?
check "exits 0 (never fails the job)" "$([ ${status} -eq 0 ] && echo ok)"
check "does NOT migrate under a running container" \
      "$(grep -q 'system migrate' "${sandbox}/calls" && echo no || echo ok)"
check "explains the wait" "$(echo "${output}" | grep -q 'another job' && echo ok)"
check "warns at the end" "$(echo "${output}" | grep -q '::warning::' && echo ok)"
rm -rf "${sandbox}"

# ------------------------------------------------------- unhealthy and idle ---
echo "case: unhealthy with nothing running"
sandbox="$(mktemp -d)"
make_sandbox "${sandbox}" 1 "" 0
output="$(run_target "${sandbox}")"
status=$?
check "exits 0" "$([ ${status} -eq 0 ] && echo ok)"
check "migrates once" \
      "$([ "$(grep -c 'system migrate' "${sandbox}/calls")" -eq 1 ] && echo ok)"
check "reports healthy afterwards" "$(echo "${output}" | grep -q 'healthy' && echo ok)"
rm -rf "${sandbox}"

# ------------------------------------------------------ migrate itself dies ---
echo "case: migrate segfaults (the #498 crash)"
sandbox="$(mktemp -d)"
make_sandbox "${sandbox}" 1 "" 2
output="$(run_target "${sandbox}")"
status=$?
check "exits 0 despite the crash" "$([ ${status} -eq 0 ] && echo ok)"
check "reports healthy afterwards" "$(echo "${output}" | grep -q 'healthy' && echo ok)"
rm -rf "${sandbox}"

# --------------------------------------------------- broken beyond repair ---
echo "case: podman stays broken"
sandbox="$(mktemp -d)"
make_sandbox "${sandbox}" 99 "" 2
output="$(run_target "${sandbox}")"
status=$?
check "still exits 0 — the container step reports the real error" \
      "$([ ${status} -eq 0 ] && echo ok)"
check "warns instead of failing" "$(echo "${output}" | grep -q '::warning::' && echo ok)"
rm -rf "${sandbox}"

echo
if [ "${failures}" -eq 0 ]; then
    echo "all checks passed"
    exit 0
fi
echo "${failures} check(s) failed"
exit 1
