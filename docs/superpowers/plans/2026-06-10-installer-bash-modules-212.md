# Installer: Run Modules via `bash` Instead of `source` (Issue #212) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix issue #212 — a full `sudo ./install.sh` run silently stops after the preflight module because modules are `source`d but terminate with `exit` — by executing modules in child `bash` processes with config passed in via exported environment and passed back via the config file.

**Architecture:** `install.sh` execs each module with `bash "$module_path"` (the exact contract `deploy/update/run-update.sh:152` already uses successfully in production). Config flows **in** through exported variables (`set -a` around config sourcing + `load_config`). Generated values flow **out** through `/etc/baluhost/install.conf`: the only two modules that generate values (`06-postgresql`: `POSTGRES_PASSWORD`; `07-env-generate`: `SECRET_KEY`, `TOKEN_SECRET`, `VPN_ENCRYPTION_KEY`) call `save_config` themselves, and `install.sh` re-runs `load_config` after every module. `save_config` is hardened with `printf '%s=%q\n'` so values with spaces/quotes (e.g. `ADMIN_PASSWORD`) survive the file round-trip.

**Tech Stack:** Bash (Debian 12/13 target; local dev via Git Bash on Windows — repo enforces `*.sh text eol=lf` in `.gitattributes`). Tests: self-contained bash harness, no root, no Debian needed.

---

## Background (read this first)

### The bug

`deploy/install/install.sh:76` runs modules with `if source "$module_path"`. Every module ends with `exit 0` (and has ~35 `exit 1` error paths). In a sourced script, `exit` terminates the **calling** shell. Consequences today:

1. Fresh full run: `run_module "01-preflight"` sources a script ending in `exit 0` → `install.sh` terminates **with exit code 0** right there. `gather_input`, modules 02–14, verification, and the completion banner never run. Silent no-op.
2. Every mid-module `exit 1` error path also kills the whole installer instead of triggering `run_module`'s "Fix the issue and re-run with `--module`" resume message.
3. Each sourced module re-sources `lib/common.sh` into the same shell, which re-runs `readonly RED=...` declarations → "readonly variable" error noise (verified non-fatal, but wrong).

### Why `bash` execution (option 3 from the issue) is safe

- Modules are already written as standalone scripts: own shebang, own `set -euo pipefail`, own `SCRIPT_DIR`, they source `lib/common.sh` themselves, and they use `exit` semantics that are **correct** under `bash` execution.
- `deploy/update/run-update.sh` (the in-app updater) already runs modules 05, 08–12 with `bash "$module_path"` after `load_config` — this contract is proven in production. `load_config` uses `set -a`, so config-file values are exported and inherited by the child.
- Full inventory of cross-module state (all 14 modules read):
  - `06-postgresql.sh:38` generates `POSTGRES_PASSWORD` → needed by 07, 08.
  - `07-env-generate.sh:19-41` generates `SECRET_KEY`, `TOKEN_SECRET`, `VPN_ENCRYPTION_KEY` → needed only by 07 itself and config persistence.
  - `05-python-venv.sh:72` exports `VENV_BIN` → consumers 08/10 have identical defaults (`${VENV_BIN:-$INSTALL_DIR/backend/.venv/bin}`), no real dependency.
  - `DATABASE_URL`: 07 rebuilds it from `POSTGRES_PASSWORD`; 08 sources `.env.production` itself. No real dependency.
  - Everything else is plain config (INSTALL_DIR, BALUHOST_USER, ADMIN_*, ENABLE_*, …) already persisted by `save_config` before the module loop.

### The new contract (document this in code comments)

```
install.sh                          module (child bash process)
──────────                          ───────────────────────────
set -a; source lib/config.sh        source lib/common.sh
load_config        ── env ──────▶   (06/07 only: source lib/config.sh; load_config)
bash modules/XX.sh                  ... work ...
                                    (06/07 only: save_config after generating)
load_config        ◀── file ─────   exit N   ← terminates only the child
```

### Out of scope (do NOT do these)

- No changes to the other 12 modules, `run-update.sh`, `ci-deploy.sh`, or any workflow file.
- No CI job for the new test (touching `.github/workflows/` triggers the CI/CD security review chain — propose as follow-up in the PR description instead).
- `save_config` writing the file briefly with default umask before `chmod 600` — pre-existing, unchanged.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `deploy/install/tests/test-install-orchestration.sh` | **Create** | Sandbox test harness: real `install.sh` + real `lib/` + stub modules in a temp dir; verifies orchestration, config round-trip, failure handling |
| `deploy/install/install.sh` | Modify | `run_module` → `bash`; export config to children; `load_config` after each module; verify script via `bash` |
| `deploy/install/lib/config.sh` | Modify | `save_config` quotes values with `printf %q` |
| `deploy/install/modules/06-postgresql.sh` | Modify | Load config itself; persist generated `POSTGRES_PASSWORD` via `save_config` |
| `deploy/install/modules/07-env-generate.sh` | Modify | Load config itself; persist generated secrets via `save_config` |

---

## Task 0: Branch Setup

- [ ] **Step 0.1: Create the fix branch off up-to-date main**

```bash
git checkout main
git pull
git checkout -b fix/installer-bash-modules-212
```

Expected: clean checkout, new branch. (If executing in an isolated worktree per `superpowers:using-git-worktrees`, create the worktree from `main` with this branch name instead.)

---

## Task 1: Test Harness (TDD red)

**Files:**
- Create: `deploy/install/tests/test-install-orchestration.sh`

- [ ] **Step 1.1: Write the test harness**

Create `deploy/install/tests/test-install-orchestration.sh` with exactly this content. Design notes baked in: it copies the **real** `install.sh` and `lib/` into a temp sandbox, appends a no-op `require_root` override to the sandbox copy of `common.sh` (tests run unprivileged; root checks are not what we're testing), and generates stub modules that are structurally faithful to real ones (shebang, `set -euo pipefail`, `source common.sh`, final `exit 0`).

```bash
#!/bin/bash
# Tests for install.sh module orchestration (issue #212).
#
# Runs the REAL install.sh + lib/ against stub modules in a temp sandbox, as
# an unprivileged user (require_root is overridden in the sandbox copy of
# common.sh — root behavior is not under test). Verifies:
#   1. A full non-interactive run executes ALL modules: a module's final
#      `exit 0` must not terminate the installer (issue #212).
#   2. Values a module persists via save_config (POSTGRES_PASSWORD from
#      stub 06) reach later modules (stub 07 asserts it).
#   3. A failing module stops the run with the resume hint and a nonzero
#      exit code; later modules do not run.
#   4. --module single mode propagates the module's exit code.
#   5. save_config/load_config round-trip values containing spaces, quotes
#      and dollar signs (ADMIN_PASSWORD is user-supplied).
#   6. A failing verify script does not suppress the completion banner.
#
# Usage: bash deploy/install/tests/test-install-orchestration.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SRC="$(cd "$TESTS_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

ALL_MODULES=(
    01-preflight 02-system-packages 03-user-setup 04-app-deploy
    05-python-venv 06-postgresql 07-env-generate 08-database-migrate
    09-frontend-build 10-systemd-services 11-nginx 12-start-services
    13-power-helpers 14-optional-features
)

make_sandbox() {
    SANDBOX=$(mktemp -d)
    cp "$INSTALL_SRC/install.sh" "$SANDBOX/"
    cp -r "$INSTALL_SRC/lib" "$SANDBOX/lib"
    mkdir -p "$SANDBOX/modules" "$SANDBOX/verify"

    # Tests run unprivileged; root is irrelevant to orchestration logic.
    echo 'require_root() { :; }' >> "$SANDBOX/lib/common.sh"

    local mod
    for mod in "${ALL_MODULES[@]}"; do
        cat > "$SANDBOX/modules/$mod.sh" <<EOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
source "\$SCRIPT_DIR/lib/common.sh"
echo "MODULE-RAN: $mod"
exit 0
EOF
    done

    # Stub 06 mirrors the real module's contract: generate a secret,
    # persist it via save_config.
    cat > "$SANDBOX/modules/06-postgresql.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
load_config
echo "MODULE-RAN: 06-postgresql"
POSTGRES_PASSWORD="stub-pw-12345"
save_config
exit 0
EOF

    # Stub 07 asserts the secret generated by 06 arrived.
    cat > "$SANDBOX/modules/07-env-generate.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
load_config
echo "MODULE-RAN: 07-env-generate"
if [[ "${POSTGRES_PASSWORD:-}" != "stub-pw-12345" ]]; then
    echo "07: POSTGRES_PASSWORD did not arrive (got: '${POSTGRES_PASSWORD:-}')" >&2
    exit 1
fi
exit 0
EOF

    # Failing verify stub — install.sh runs it with `|| true`, so the
    # completion banner must still appear.
    cat > "$SANDBOX/verify/verify-install.sh" <<'EOF'
#!/bin/bash
echo "VERIFY-RAN"
exit 1
EOF
}

cleanup() { rm -rf "$SANDBOX"; }

# ─── Tests 1 + 2 + 6: full run, config round-trip, verify tolerance ──────────

make_sandbox
CONF="$SANDBOX/install.conf"
OUTPUT=$(bash "$SANDBOX/install.sh" --non-interactive --config "$CONF" 2>&1)
RC=$?

if [[ $RC -eq 0 ]]; then pass "full run exits 0"; else fail "full run exited $RC"; fi
for mod in "${ALL_MODULES[@]}"; do
    if grep -q "MODULE-RAN: $mod" <<<"$OUTPUT"; then
        pass "module $mod ran"
    else
        fail "module $mod did NOT run"
    fi
done
if grep -q "Installation Complete" <<<"$OUTPUT"; then
    pass "completion banner shown"
else
    fail "completion banner missing"
fi
if grep -q "VERIFY-RAN" <<<"$OUTPUT"; then
    pass "verify script ran (failing verify tolerated)"
else
    fail "verify script did not run"
fi
if grep -q 'POSTGRES_PASSWORD=stub-pw-12345' "$CONF" 2>/dev/null; then
    pass "POSTGRES_PASSWORD persisted to config file"
else
    fail "POSTGRES_PASSWORD missing from config file"
fi
cleanup

# ─── Test 3: failing module stops the run; later modules skipped ─────────────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/modules/05-python-venv.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
echo "MODULE-RAN: 05-python-venv"
echo "boom" >&2
exit 1
EOF
OUTPUT=$(bash "$SANDBOX/install.sh" --non-interactive --config "$CONF" 2>&1)
RC=$?
if [[ $RC -ne 0 ]]; then pass "failed run exits nonzero"; else fail "failed run exited 0"; fi
if grep -q "Installation stopped at module: 05-python-venv" <<<"$OUTPUT"; then
    pass "stop message with resume hint shown"
else
    fail "stop message missing"
fi
if ! grep -q "MODULE-RAN: 06-postgresql" <<<"$OUTPUT"; then
    pass "later modules skipped after failure"
else
    fail "later modules ran after failure"
fi
cleanup

# ─── Test 4: --module single mode propagates exit code ──────────────────────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/modules/05-python-venv.sh" <<'EOF'
#!/bin/bash
exit 7
EOF
bash "$SANDBOX/install.sh" --module 05-python-venv --config "$CONF" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 7 ]]; then
    pass "--module propagates module exit code (7)"
else
    fail "--module exit code was $RC (expected 7)"
fi
cleanup

# ─── Test 5: save_config/load_config round-trip with special characters ─────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/roundtrip.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
ADMIN_PASSWORD='p@ss word$1"x'
save_config
ADMIN_PASSWORD=""
load_config
if [[ "$ADMIN_PASSWORD" == 'p@ss word$1"x' ]]; then
    echo "ROUNDTRIP-OK"
else
    echo "round-trip mismatch: '$ADMIN_PASSWORD'" >&2
    exit 1
fi
EOF
RT_OUTPUT=$(BALUHOST_CONFIG="$CONF" bash "$SANDBOX/roundtrip.sh" 2>&1)
if grep -q "ROUNDTRIP-OK" <<<"$RT_OUTPUT"; then
    pass "config round-trip preserves special characters"
else
    fail "config round-trip broke special characters: $RT_OUTPUT"
fi
cleanup

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
```

- [ ] **Step 1.2: Verify the file parses and has LF line endings**

The repo enforces `*.sh text eol=lf` via `.gitattributes`, but the working-tree file must be LF **now** for Git Bash to run it (CRLF breaks bash). Run:

```bash
cd "/d/Programme (x86)/Baluhost"
bash -n deploy/install/tests/test-install-orchestration.sh && echo SYNTAX-OK
grep -c $'\r' deploy/install/tests/test-install-orchestration.sh || echo NO-CR
```

Expected: `SYNTAX-OK` and `NO-CR` (grep finds zero CR characters; non-zero count means convert with `dos2unix` or rewrite).

- [ ] **Step 1.3: Run the test to verify it fails (red)**

```bash
bash deploy/install/tests/test-install-orchestration.sh
```

Expected: **FAIL**, exit code 1. Specifically with the current `source`-based `install.sh`:
- "full run exits 0" PASSes (deceptively — that IS the bug: silent no-op with exit 0),
- "module 01-preflight ran" PASSes, but "module 02-system-packages ran" through "module 14-optional-features ran" all FAIL (the sourced stub's `exit 0` killed the installer),
- "completion banner missing" FAILs, "POSTGRES_PASSWORD missing from config file" FAILs,
- Test 5 round-trip FAILs (current `save_config` writes unquoted values).
- `readonly variable` warnings appear in output noise (modules re-sourcing `common.sh` into the same shell) — expected pre-fix.

Do NOT commit yet — commit lands with the green implementation in Task 3.

---

## Task 2: `install.sh` — execute modules in child processes

**Files:**
- Modify: `deploy/install/install.sh`

- [ ] **Step 2.1: Export config defaults to child processes**

Replace lines 10–13:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
source "$SCRIPT_DIR/lib/features.sh"
```

with:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
# set -a: export the config defaults so they reach the child bash processes
# that run_module spawns (same env-based contract as run-update.sh). Verified:
# bash gives := expansions under set -a the export attribute. The
# save_config + load_config round-trip before the module loop additionally
# guarantees every value is exported regardless of how it was assigned.
set -a
source "$SCRIPT_DIR/lib/config.sh"
set +a
source "$SCRIPT_DIR/lib/features.sh"
```

- [ ] **Step 2.2: Run modules with `bash` instead of `source`**

In `run_module()` (currently lines 74–83), replace:

```bash
    log_step "Running module: $module_name"
    # Source the module so it inherits our environment (config variables)
    if source "$module_path"; then
```

with:

```bash
    log_step "Running module: $module_name"
    # Execute the module in a child bash process (same contract as
    # deploy/update/run-update.sh). Config flows IN via exported variables;
    # generated values flow OUT via the config file (modules 06/07 call
    # save_config, the loop below re-runs load_config). Executing instead of
    # sourcing keeps a module's `exit` from terminating the installer (#212).
    if bash "$module_path"; then
```

- [ ] **Step 2.3: Export `--config` and `--non-interactive` to children**

In the argument parsing in `main()` (currently lines 189–196), replace:

```bash
            --config)
                BALUHOST_CONFIG="$2"
                shift 2
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
```

with:

```bash
            --config)
                BALUHOST_CONFIG="$2"
                export BALUHOST_CONFIG
                shift 2
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                export NON_INTERACTIVE
                shift
                ;;
```

- [ ] **Step 2.4: Re-load config around the module loop**

Replace the block (currently lines 236–254):

```bash
    # Gather user input
    gather_input

    # Save config before running modules (so we can resume on failure)
    save_config

    # Run modules 02-12
    local failed=0
    for mod in "${MODULES[@]:1}"; do  # Skip 01-preflight (already ran)
        if ! run_module "$mod"; then
            failed=1
            log_error "Installation stopped at module: $mod"
            log_error "Fix the issue and re-run: sudo $0 --module $mod"
            log_error "Then resume full install: sudo $0"
            break
        fi
        # Save config after each module (captures generated values like POSTGRES_PASSWORD)
        save_config
    done
```

with:

```bash
    # Gather user input
    gather_input

    # Save config before running modules (so we can resume on failure), then
    # re-load it: load_config uses `set -a`, which guarantees every value —
    # including interactive input — is exported to the module child processes.
    save_config
    load_config

    # Run modules 02-14
    local failed=0
    for mod in "${MODULES[@]:1}"; do  # Skip 01-preflight (already ran)
        if ! run_module "$mod"; then
            failed=1
            log_error "Installation stopped at module: $mod"
            log_error "Fix the issue and re-run: sudo $0 --module $mod"
            log_error "Then resume full install: sudo $0"
            break
        fi
        # Re-load config so values a module persisted (POSTGRES_PASSWORD from
        # 06, secrets from 07) are exported to the next module.
        load_config
    done
```

- [ ] **Step 2.5: Run the verify script with `bash` too**

`verify/verify-install.sh` also ends with `exit` — same source bug. Replace (currently lines 259–261):

```bash
        if [[ -f "$SCRIPT_DIR/verify/verify-install.sh" ]]; then
            source "$SCRIPT_DIR/verify/verify-install.sh" || true
        fi
```

with:

```bash
        if [[ -f "$SCRIPT_DIR/verify/verify-install.sh" ]]; then
            bash "$SCRIPT_DIR/verify/verify-install.sh" || true
        fi
```

- [ ] **Step 2.6: Syntax check + partial test run**

```bash
bash -n deploy/install/install.sh && echo SYNTAX-OK
bash deploy/install/tests/test-install-orchestration.sh
```

Expected: `SYNTAX-OK`. Test results: all of tests 1–4 and 6 PASS (all 14 modules run, banner shown, config round-trip via stubs works, failure handling works, exit-code propagation works). **Test 5 (special characters) still FAILs** — `save_config` is hardened in Task 3.

---

## Task 3: `save_config` quoting hardening

**Files:**
- Modify: `deploy/install/lib/config.sh`

**Why in scope:** the config file becomes the only module→installer transport channel, and `ADMIN_PASSWORD` is user-supplied free text. Today's unquoted `VAR=value` lines break `load_config` for values with spaces/quotes (pre-existing on the resume path; now load-bearing).

- [ ] **Step 3.1: Replace `save_config` with a `printf %q` version**

In `deploy/install/lib/config.sh`, replace the whole `save_config()` function (currently lines 61–98):

```bash
save_config() {
    local config_dir
    config_dir=$(dirname "$BALUHOST_CONFIG")
    mkdir -p "$config_dir"

    # %q-quote every value so load_config can source the file safely even
    # when values (e.g. ADMIN_PASSWORD) contain spaces, quotes or $.
    # DATABASE_URL is deliberately NOT persisted: it is derived state that
    # embeds POSTGRES_PASSWORD (module 07 rebuilds it; module 08 reads
    # .env.production) — persisting it would duplicate the secret.
    local -a config_vars=(
        INSTALL_DIR BALUHOST_USER BALUHOST_GROUP FRONTEND_STATIC_DIR
        POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
        ADMIN_USERNAME ADMIN_PASSWORD ADMIN_EMAIL
        SECRET_KEY TOKEN_SECRET VPN_ENCRYPTION_KEY
        GIT_REPO GIT_BRANCH
        ENABLE_RAID ENABLE_SMART ENABLE_VPN ENABLE_CLOUD
        ENABLE_SAMBA ENABLE_NFS ENABLE_WSDD ENABLE_MDNS
    )

    {
        echo "# BaluHost Install Configuration"
        echo "# Generated: $(date -Iseconds)"
        echo "# Mode 600 — do not share this file."
        echo ""
        local var
        for var in "${config_vars[@]}"; do
            printf '%s=%q\n' "$var" "${!var:-}"
        done
    } > "$BALUHOST_CONFIG"

    chmod 600 "$BALUHOST_CONFIG"
    log_info "Config saved to $BALUHOST_CONFIG (mode 600)"
}
```

Compatibility note: `load_config` just sources the file, so old-format (unquoted) config files on existing boxes keep loading; the first `save_config` rewrites them in the new format. Plain alphanumeric values are emitted unchanged by `%q` (the test's `POSTGRES_PASSWORD=stub-pw-12345` grep still matches).

- [ ] **Step 3.2: Run the full test suite — all green**

```bash
bash -n deploy/install/lib/config.sh && echo SYNTAX-OK
bash deploy/install/tests/test-install-orchestration.sh
```

Expected: `SYNTAX-OK`, then all tests PASS, summary line `Results: 23 passed, 0 failed` (18 from the full run, 3 from failure handling, 1 exit-code propagation, 1 round-trip), exit code 0.

- [ ] **Step 3.3: Commit the orchestration fix**

```bash
git add deploy/install/tests/test-install-orchestration.sh deploy/install/install.sh deploy/install/lib/config.sh
git commit -m "fix(install): run installer modules in child bash processes (#212)

Sourced modules end with 'exit', which terminated install.sh after the
preflight module — a fresh full run was a silent no-op (exit 0). Modules
now execute via 'bash' (the contract run-update.sh already uses): config
flows in through exported variables and back out through install.conf.
save_config %q-quotes values so user-supplied passwords survive the file
round-trip. Adds a sandboxed orchestration test harness."
```

---

## Task 4: Modules 06/07 persist their generated values

**Files:**
- Modify: `deploy/install/modules/06-postgresql.sh`
- Modify: `deploy/install/modules/07-env-generate.sh`

These are the only two modules that generate values consumed outside themselves. In a child process, their `export`s die with the process — they must persist via `save_config`. (The sandbox stubs in Task 1 encode this exact contract; the real modules can't be exercised by the harness, so verification here is `bash -n` + review.)

- [ ] **Step 4.1: `06-postgresql.sh` — load config, persist generated password**

Replace lines 1–5:

```bash
#!/bin/bash
# BaluHost Install - Module 06: PostgreSQL Setup
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
```

with:

```bash
#!/bin/bash
# BaluHost Install - Module 06: PostgreSQL Setup
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
load_config
```

Then replace the password generation block (currently lines 36–41):

```bash
# --- Generate password if not set ---
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD=$(generate_db_password)
    log_info "Generated random PostgreSQL password."
    export POSTGRES_PASSWORD
fi
```

with:

```bash
# --- Generate password if not set ---
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD=$(generate_db_password)
    log_info "Generated random PostgreSQL password."
    export POSTGRES_PASSWORD
    # This module runs in a child process of install.sh — the generated
    # password reaches later modules only via the config file (#212).
    save_config
fi
```

- [ ] **Step 4.2: `07-env-generate.sh` — load config, persist generated secrets**

Replace lines 1–5 (identical pattern):

```bash
#!/bin/bash
# BaluHost Install - Module 07: Environment File Generation
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
```

with:

```bash
#!/bin/bash
# BaluHost Install - Module 07: Environment File Generation
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"
load_config
```

Then, directly after the third secret-generation block (currently ends at line 41 with the `VPN_ENCRYPTION_KEY` `fi`), insert before the `# --- Build DATABASE_URL ---` comment:

```bash
# This module runs in a child process of install.sh — generated secrets
# reach the orchestrator and any resumed run only via the config file (#212).
save_config

```

- [ ] **Step 4.3: Syntax checks + full test suite still green**

```bash
bash -n deploy/install/modules/06-postgresql.sh && echo 06-OK
bash -n deploy/install/modules/07-env-generate.sh && echo 07-OK
bash deploy/install/tests/test-install-orchestration.sh
```

Expected: `06-OK`, `07-OK`, all tests PASS.

- [ ] **Step 4.4: Commit**

```bash
git add deploy/install/modules/06-postgresql.sh deploy/install/modules/07-env-generate.sh
git commit -m "fix(install): modules 06/07 persist generated secrets via save_config (#212)

Running in a child process, their exports no longer reach install.sh;
the config file is the transport channel. load_config at module start
also makes standalone --module runs read the same state."
```

---

## Task 5: Final Verification

- [ ] **Step 5.1: Syntax-check every touched script + full suite**

```bash
for f in deploy/install/install.sh deploy/install/lib/config.sh \
         deploy/install/modules/06-postgresql.sh \
         deploy/install/modules/07-env-generate.sh \
         deploy/install/tests/test-install-orchestration.sh; do
    bash -n "$f" || echo "SYNTAX FAIL: $f"
done
bash deploy/install/tests/test-install-orchestration.sh
```

Expected: no `SYNTAX FAIL` lines; `Results: 23 passed, 0 failed`.

- [ ] **Step 5.2: shellcheck (if available — skip gracefully if not installed)**

```bash
command -v shellcheck >/dev/null && shellcheck deploy/install/install.sh deploy/install/lib/config.sh deploy/install/modules/06-postgresql.sh deploy/install/modules/07-env-generate.sh deploy/install/tests/test-install-orchestration.sh || echo "shellcheck not installed — skipped"
```

Expected: no errors (info/style notes acceptable if consistent with existing code).

- [ ] **Step 5.3: Review the diff against the CI/CD security reviewer checklist**

The change touches `/deploy/` (CODEOWNERS-flagged). Confirm from `git diff main --stat`:
- No workflow files touched, no new `runs-on`, no new sudoers/systemd template changes, no new secrets references, no changes to `ci-deploy.sh`.
- `run-update.sh` untouched — it runs modules 05/08–12, none of which changed.

---

## Task 6: Pull Request

- [ ] **Step 6.1: Push and open the PR**

Write the PR body to a temp file with the Write tool first (here-strings break in both Bash and PowerShell tools on this machine), then:

```bash
git push -u origin fix/installer-bash-modules-212
gh pr create --base main --title "fix(install): run installer modules in child bash processes (#212)" --body-file <bodyfile>
```

PR body must cover: the bug (silent stop after preflight, exit 0), the chosen fix (option 3 — matches the proven `run-update.sh` contract), why this also fixes all mid-module `exit 1` error paths + readonly re-source noise, the `save_config` `%q` hardening rationale, the new test harness and how to run it, the note that real Debian end-to-end installs remain untested by CI (follow-up idea: run the orchestration test in CI — deliberately left out to avoid touching workflows in this PR), and `Closes #212`.

---

## Self-Review Notes (already applied)

- **Spec coverage:** issue #212 fix (Task 2), single-module mode preserved (test 4), resume-on-failure preserved (`save_config` pre-loop + `load_config` per module, test 3), verify-script same-bug fix (Step 2.5, test 6), secrets transport (Task 4, test 2), quoting hardening (Task 3, test 5).
- **Type consistency:** stub modules in the harness use the exact contract Task 4 implements (`source lib/config.sh; load_config; ...; save_config`).
- **Known accepted quirks:** `load_config` log lines now appear once per module (noise, harmless). Old-format config files load unchanged. `gather_input`'s `confirm "Proceed with installation?"` → `exit 0` on decline is in `install.sh` itself, not sourced — unaffected.
- **Execution note (2026-06-10):** during implementation a code-quality review found that the `source`→`bash` switch UN-masks the `((PASS++))` errexit trap in `verify/verify-install.sh` (previously suppressed by `source ... || true`) — fixed in-PR, with a regression-guard assertion in the harness (final count: 24, not 23). `save_config` additionally hardened: tmp-file + chmod-before-write + mv (atomic, never world-readable), `export -fn load_config save_config` strips the helper functions from child environments.
- **Reviewed 2026-06-10 (subagent review, findings incorporated):** no blockers. `DATABASE_URL` omission from `save_config` is now documented in-code (derived state embedding the DB secret). The reviewer's claim that `:=` expansions under `set -a` don't get exported was tested and found wrong (bash does export them) — `set -a` stays, comment clarified. Expected test count corrected to 23. **Side-finding (pre-existing, NOT in scope):** `verify/verify-install.sh` uses `((PASS++))` under `set -euo pipefail` — the first increment from 0 returns exit 1 and aborts the script; today masked by `|| true`. Candidate for a separate GitHub issue.
