#!/usr/bin/env bash
#
# Bring the shared rootless Podman state on the ci-sandbox pool into a usable
# shape — without ever taking the job down with it.
#
# Why this exists (#394, #436, #498)
# ----------------------------------
# BaluNode-ci-sandbox and BaluNode-ci-sandbox-2 run as the SAME POSIX user
# (ci-runner), so all three sandbox jobs share ONE rootless Podman state,
# including the pause process that holds the user namespace. A job that starts
# while another job's podman is coming up loses that race and dies before any
# test runs ("invalid internal status ... could not find any running process").
# #436 serialized the check with flock, which fixed the race on the PROBE.
#
# It did not fix the REPAIR. `podman system migrate` stops every running
# container as part of resetting the pause process, and on 2026-08-01 it did
# exactly that to a container left over from another job and then segfaulted
# tearing down its network:
#
#     stopped d8993442c3fc...
#     panic: runtime error: invalid memory address or nil pointer dereference
#     [signal SIGSEGV] libpod.(*Runtime).Migrate -> teardownNetworkBackend
#     ##[error]Process completed with exit code 2
#
# The job was red 7 seconds in, before installing anything. The guard in place
# then was "only migrate when podman is broken" — but a broken `podman info`
# says nothing about whether containers are running, which is what makes
# migrate destructive.
#
# What this does differently
# --------------------------
#   1. probe first; a healthy runtime needs no repair at all
#   2. if it is unhealthy but containers are running, WAIT — another job is
#      mid-flight and migrating would rip the floor out from under it
#   3. migrate only when unhealthy AND nothing is running
#   4. never propagate migrate's exit code. A crash while cleaning up is not a
#      reason to fail this job; what matters is whether podman works afterwards
#   5. never exit non-zero at all. If podman is still unusable, the container
#      step that follows fails on its own with a far more specific message
#      than "the health check said no"
#
# Called from the three sandbox jobs (ci-check.yml x2, playwright-e2e.yml)
# under a shared flock, so only one instance of this runs at a time.

# NOT `set -e`: every failure in here is something to inspect and report, not
# something to die on. That is the whole point of the script.
set -uo pipefail

# Overridable so the behaviour can be exercised without waiting half a minute
# (scripts/tests/test-ci-podman-health.sh). Nothing in CI sets them; the worst
# a wrong value can do is wait longer or shorter.
: "${PODMAN_HEALTH_MAX_ATTEMPTS:=6}"
: "${PODMAN_HEALTH_BUSY_WAIT:=5}"
: "${PODMAN_HEALTH_SETTLE:=2}"

readonly MAX_ATTEMPTS="${PODMAN_HEALTH_MAX_ATTEMPTS}"
readonly BUSY_WAIT_SECONDS="${PODMAN_HEALTH_BUSY_WAIT}"
readonly SETTLE_SECONDS="${PODMAN_HEALTH_SETTLE}"

log() { echo "podman-health: $*"; }

is_healthy() {
    podman info >/dev/null 2>&1
}

# Are containers running RIGHT NOW? Asked two ways on purpose: `podman ps`
# needs a working runtime, which is exactly what we cannot assume here, while
# conmon (one process per running container) is visible in the process table no
# matter how confused podman itself is.
containers_running() {
    if command -v pgrep >/dev/null 2>&1 && pgrep -u "$(id -u)" -x conmon >/dev/null 2>&1; then
        return 0
    fi
    [ -n "$(podman ps -q 2>/dev/null)" ]
}

main() {
    for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
        if is_healthy; then
            [ "${attempt}" -eq 1 ] && log "healthy" || log "healthy after ${attempt} attempts"
            return 0
        fi

        if containers_running; then
            log "unhealthy, but containers are running — another job is using this podman."
            log "waiting ${BUSY_WAIT_SECONDS}s instead of migrating (attempt ${attempt}/${MAX_ATTEMPTS})"
            sleep "${BUSY_WAIT_SECONDS}"
            continue
        fi

        log "unhealthy and nothing running — resetting the pause process (attempt ${attempt}/${MAX_ATTEMPTS})"
        if ! podman system migrate 2>&1 | sed 's/^/podman-health:   /'; then
            # Includes the SIGSEGV from #498. Deliberately swallowed: the next
            # probe decides, not the exit code of the cleanup.
            log "migrate reported a failure — checking whether podman works anyway"
        fi
        sleep "${SETTLE_SECONDS}"
    done

    if is_healthy; then
        log "healthy"
        return 0
    fi

    # A warning, not an error: if podman really is unusable, the podman run
    # step fails next with a specific message. Failing here would only replace
    # that message with a vaguer one.
    echo "::warning::rootless podman still reports unhealthy after ${MAX_ATTEMPTS} attempts — the container step may fail"
    return 0
}

main "$@"
