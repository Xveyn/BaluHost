# Plugin Backend Isolation — Phase 5a: Hardened Worker Spawn

**Status:** Spec
**Date:** 2026-06-28
**Track:** Plugin-Sandboxing Track B (Backend Python Isolation), Phase 5a
**Predecessors:** Phase 1–4 merged (PRs #282–#285). Phase 4 wired external
plugins to a sandboxed subprocess via an injectable `SpawnHook`; the hook is
currently the unhardened `_default_spawn` stub.
**Sibling:** Phase 5b (frontend documentation + scope-picker UI +
`get_ui_manifest` external-plugin gap) — separate spec/plan/PR.

## Problem

External (marketplace) plugins already run in an isolated subprocess
(`SandboxSupervisor`), reached only through a token-free host proxy with
default-deny capabilities. But the subprocess itself still runs with the **full
privileges of the backend service user** (`baluhost`):

- It **inherits the backend's environment** — including every secret loaded from
  `.env.production` via the systemd `EnvironmentFile` (`SECRET_KEY`,
  `*_ENCRYPTION_KEY`, DB DSN, …). `asyncio.create_subprocess_exec` passes
  `os.environ` by default. A malicious plugin reads its own `os.environ` and has
  every host secret.
- It runs as `baluhost`, so it can **read/write everything `baluhost` can**:
  NAS storage, config, other plugins' data.
- It has **unrestricted network egress** — a malicious plugin can exfiltrate
  whatever it scrapes.
- It has **no resource limits** — a fork bomb or memory balloon degrades the
  whole NAS; the supervisor's restart budget only catches a *clean* exit.

The `SpawnHook` seam (`supervisor.py:29`) was designed in Phase 2b precisely so
this hardening slots in without touching `SandboxSupervisor`. Phase 5a fills it.

Greenfield: **0 external plugins are deployed today.** This is proactive
hardening before the ecosystem grows — nothing in production breaks.

## Goals

- Spawn external plugin workers as an **unprivileged, dedicated OS user**
  (`baluhost-plugin`) with **no sudo, no NAS-storage read, no secret read**.
- **Scrub the environment** so the worker never inherits `.env.production`
  secrets — pass a minimal, fixed allowlist.
- **Network-isolate** the worker (`unshare --net`) — no egress; the UDS socket
  the host created remains reachable (it is a filesystem object, not network).
- **Resource-limit** the worker (CPU, address space, process count, file size)
  so a malicious plugin cannot fork-bomb or OOM the host.
- **Fail closed in production:** if hardening is required (prod + Linux) but the
  box is not yet provisioned, **refuse to spawn** external plugins rather than
  run them unhardened.
- Keep **dev (Windows / non-prod Linux) on the existing `_default_spawn`** so
  local development is unchanged.
- Fold in robustness **Fix-A**: `disable_plugin` must not orphan a subprocess if
  `supervisor.stop()` raises.

## Non-Goals

- **Mount/PID/IPC namespaces, seccomp, cgroup v2 quotas.** Deliberately deferred
  — they add real cross-distro fragility for marginal gain over user-drop +
  netns + rlimits against the realistic plugin threats (exfil, fork-bomb, OOM,
  secret theft). May be revisited if the ecosystem warrants it.
- **Bundled (first-party) plugins.** They stay in-process and trusted, exactly
  as before. Phase 5a only touches the external/sandboxed spawn path.
- **Frontend changes, scope-picker UI, `get_ui_manifest` external gap.** → 5b.
- **Track C (signing).** Separate track.
- **Windows production hardening.** BaluHost production is Linux; Windows is a
  dev-only target and keeps `_default_spawn`.

## Architecture

```
manager._enable_external(name, discovered, granted_api_scopes)
  │
  ├─ _supervisor_factory(name, dir, router)
  │     spawn_hook = select_spawn_hook()        ← NEW: auto-detect
  │     SandboxSupervisor(..., spawn_hook=spawn_hook)
  │
  └─ if prod+Linux and spawn_hook is None:      ← NEW: fail-closed
        refuse (False) + ERROR log + audit; do NOT spawn

SandboxSupervisor._spawn_and_connect()          (unchanged)
  argv = [python, -m, app.plugins.sandbox.worker, --connect <addr>,
          --plugin-dir <dir>, --plugin-name <name>]
  process = await spawn_hook(argv, cwd)
        │
        ├─ _default_spawn (dev/Windows/non-prod) ── create_subprocess_exec(*argv)
        │
        └─ hardened_spawn (prod Linux, provisioned)                 ← NEW
              env = scrub_env()                  ← minimal allowlist, no secrets
              wrapped = [sudo, -n, WRAPPER_PATH, *argv]
              create_subprocess_exec(*wrapped, cwd=cwd, env=env)
                    │
                    ▼
        /opt/baluhost/deploy/bin/spawn-plugin-worker.sh  (root:root 0755)
              validate: plugin-dir under canonical external dir (realpath+prefix)
              validate: plugin-name ^[a-z0-9_]+$
              exec setpriv --reuid baluhost-plugin --regid baluhost-plugin \
                    --init-groups --rlimit-... \
                    unshare --net -- <venv-python> -m app.plugins.sandbox.worker ...
```

The worker process is unchanged. It connects back over the UDS socket the host
already created and answers the health handshake — identical to today, just from
inside a netns as a different, unprivileged user.

## Components & Files

### Backend

**`backend/app/plugins/sandbox/spawn.py` (NEW)**

```python
async def hardened_spawn(argv: list[str], cwd: str) -> asyncio.subprocess.Process:
    """Spawn the worker through the root-owned sudo wrapper, dropping to
    baluhost-plugin in a network namespace with rlimits, with a scrubbed env."""

def scrub_env() -> dict[str, str]:
    """Minimal environment for the worker — never inherits os.environ.
    Allowlist only: PATH, LANG, LC_ALL, PYTHONUNBUFFERED, PYTHONDONTWRITEBYTECODE.
    Explicitly excludes every *.env.production secret."""

def select_spawn_hook() -> SpawnHook | None:
    """Return the spawn hook appropriate for this host, or None when hardening
    is required but unavailable.

    - dev / non-prod / Windows  → _default_spawn (unchanged local behavior)
    - prod + Linux + wrapper executable present + baluhost-plugin user exists
                                → hardened_spawn
    - prod + Linux + not provisioned
                                → None  (caller fails closed)
    """
```

- `scrub_env()` builds the env from a fixed allowlist read from the *current*
  `os.environ` (so `PATH` points at the venv) but copies **only** the allowlisted
  keys. No secret key can pass.
- `select_spawn_hook()` uses `settings.is_production`, `sys.platform`,
  `os.access(settings.plugin_sandbox_wrapper_path, os.X_OK)`, and a
  `pwd.getpwnam(settings.plugin_sandbox_user)` probe (guarded — `pwd` is
  POSIX-only). The probe result is computed once at call time (not cached at
  import) so a freshly-provisioned box is picked up on the next plugin enable /
  worker reload without a process restart.

**`backend/app/plugins/manager.py`**

- `_supervisor_factory` passes `spawn_hook=select_spawn_hook()` into
  `SandboxSupervisor`. Because `select_spawn_hook()` may return `None`, the
  factory and `_enable_external` coordinate via a small helper:

```python
def _supervisor_factory(self, plugin_name, plugin_dir, capability_router):
    from app.plugins.sandbox.spawn import select_spawn_hook
    hook = select_spawn_hook()
    if hook is None and _hardening_required():     # prod + Linux
        raise SandboxHardeningUnavailable(plugin_name)
    kwargs = {"capability_router": capability_router}
    if hook is not None:
        kwargs["spawn_hook"] = hook
    return SandboxSupervisor(plugin_name, plugin_dir, **kwargs)
```

- `_enable_external` catches `SandboxHardeningUnavailable`, logs an ERROR, writes
  an audit event (`plugin_sandbox_hardening_unavailable`), and returns `False`
  (fail closed). Dev/Windows is never affected because `_hardening_required()` is
  False there.
- When `hook is None` but hardening is **not** required (dev/Windows), the
  factory omits `spawn_hook` so `SandboxSupervisor`'s default (`_default_spawn`)
  applies — existing behavior, byte-for-byte.

**Fix-A — `disable_plugin` orphan guard**

Current code pops the supervisor *before* awaiting `stop()`; if `stop()` raises,
the only handle is gone and the child can leak. Fix:

```python
if name in self._sandboxes:
    supervisor = self._sandboxes[name]
    try:
        await supervisor.stop()
    except Exception:
        logger.exception("Error stopping sandbox for %s; forcing kill", name)
        await supervisor._hard_kill()        # ensure no orphan
    finally:
        self._sandboxes.pop(name, None)
        self._enabled.discard(name)
    logger.info("Disabled external (sandboxed) plugin: %s", name)
    return True
```

(`_hard_kill()` already exists on `SandboxSupervisor` and is idempotent — it
closes the channel and SIGKILLs the process if still alive.)

> **Note — Follow-up B is already satisfied (verify-only, no code).**
> `SandboxSupervisor.start()` calls `_spawn_and_connect()`, which invokes
> `_hard_kill()` on both the accept-timeout and the health-handshake-failure
> paths *before* raising, and the supervise task is only created *after* a
> successful connect. So a failed `start()` in `_enable_external` already leaves
> no child behind. The plan records this as a verification step, not a change.

### Config

**`backend/app/core/config.py`**

- `plugin_sandbox_user: str = "baluhost-plugin"`
- `plugin_sandbox_wrapper_path: str = "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"`

Both are plain settings (no production validator — they have safe defaults and
are only consulted on Linux prod). Documented in `.env.example`.

### Deploy

**`deploy/install/bin/spawn-plugin-worker.sh` (NEW — root:root, mode 0755)**

The only thing `baluhost` may invoke via sudo. Hardened:

```bash
#!/bin/bash
set -euo pipefail

# Fixed, trusted constants — NOT taken from the caller.
EXTERNAL_DIR="/var/lib/baluhost/plugins"
PLUGIN_USER="baluhost-plugin"
VENV_PYTHON="/opt/baluhost/backend/.venv/bin/python"
WORKER_MODULE="app.plugins.sandbox.worker"

# Parse only the flags we expect; reject anything else.
connect="" plugin_dir="" plugin_name=""
# ... explicit --connect/--plugin-dir/--plugin-name parsing via case "$1" ...

# Validate plugin-name: strict allowlist.
[[ "$plugin_name" =~ ^[a-z0-9_]+$ ]] || { echo "bad plugin-name" >&2; exit 64; }

# Validate plugin-dir: must canonicalize to <EXTERNAL_DIR>/<plugin_name>.
real_dir="$(realpath -e -- "$plugin_dir")" || exit 65
[[ "$real_dir" == "$EXTERNAL_DIR/$plugin_name" ]] || { echo "dir outside jail" >&2; exit 66; }

# Validate connect address: no shell metacharacters (UDS path or host:port).
[[ "$connect" =~ ^[A-Za-z0-9_./:@-]+$ ]] || { echo "bad connect" >&2; exit 67; }

exec setpriv --reuid "$PLUGIN_USER" --regid "$PLUGIN_USER" --init-groups \
     --rlimit-cpu=... --rlimit-as=... --rlimit-nproc=... --rlimit-fsize=... \
  unshare --net -- \
     "$VENV_PYTHON" -m "$WORKER_MODULE" \
        --connect "$connect" --plugin-dir "$real_dir" --plugin-name "$plugin_name"
```

Key properties (each maps to a CI-CD reviewer-checklist item):
- sudoers points at this **exact path** with **no args pinned** — safe because
  the wrapper itself validates every argument and ignores anything unexpected.
- Constants (`EXTERNAL_DIR`, `VENV_PYTHON`, user) are **hardcoded**, never from
  the caller — the caller only influences `--connect/--plugin-dir/--plugin-name`,
  all validated.
- `realpath -e` + exact-match prevents `..`/symlink escape of the external dir.
- `setpriv --init-groups` drops to exactly `baluhost-plugin`'s groups (not
  `baluhost`'s), so no NAS-storage read.
- Concrete rlimit values are chosen in the plan (e.g. CPU 60s soft, AS 512 MiB,
  nproc 64, fsize 64 MiB) and documented.

**`deploy/install/templates/baluhost-plugin-sudoers` (NEW)**

```
baluhost ALL=(root) NOPASSWD: /opt/baluhost/deploy/bin/spawn-plugin-worker.sh
```

Installed by the existing module-10 pattern (`process_template` → `chmod 440` →
`visudo -cf` validate → roll back on syntax error). `%BALUHOST_USER%` templated.

**`deploy/install/modules/03-user-setup.sh`**

- Create system user `baluhost-plugin`: `useradd --system --no-create-home
  --shell /usr/sbin/nologin`, primary group `baluhost-plugin`. **Not** in the
  `baluhost` group (no storage/secret read), **not** in `sudo`/`docker`/`wheel`.
- Add `baluhost` to the `baluhost-plugin` group (so the host can create a
  group-connectable UDS socket the worker can reach, and so the external plugins
  dir is shared).
- Ensure `/var/lib/baluhost/plugins` exists, owned `baluhost:baluhost-plugin`,
  mode `0750` (baluhost rwx, baluhost-plugin r-x → traverse + read plugin code +
  connect socket; world none).
- Ensure `.env.production` is `0640 baluhost:baluhost` (baluhost-plugin not in
  `baluhost` group → cannot read it). Defense in depth on top of env-scrubbing.

**`deploy/install/bin/` install step**

A module (extend module 10 or a small dedicated block) copies
`spawn-plugin-worker.sh` to `/opt/baluhost/deploy/bin/`, `chown root:root`,
`chmod 0755`, and runs `bash -n` to syntax-check it.

### Socket / filesystem access model

| Object | Owner / mode | baluhost-plugin can |
|---|---|---|
| `/var/lib/baluhost/plugins/<name>/` | `baluhost:baluhost-plugin` `0750` | traverse + read (code, site-packages) |
| UDS socket (host-created in plugin dir) | `baluhost:baluhost-plugin`, group-connectable | connect |
| `/opt/baluhost/backend` (venv + app code) | group/world readable; not secret | read (run the worker) |
| `/opt/baluhost/.env.production` | `baluhost:baluhost` `0640` | **no** |
| NAS storage mountpoints | `baluhost:baluhost` | **no** (not in group) |

The worker reads only code; secrets reach it through neither the filesystem
(ownership) nor the environment (scrubbing).

## Data Flow

1. `manager._enable_external` → `_supervisor_factory` → `select_spawn_hook()`.
2. Prod Linux, provisioned → `hardened_spawn`; supervisor stores it.
3. `supervisor.start()` → `_spawn_and_connect()` builds the worker argv,
   calls `hardened_spawn(argv, cwd)`.
4. `hardened_spawn` scrubs env, prepends `sudo -n <wrapper>`, spawns.
5. Wrapper validates args, `setpriv`-drops to `baluhost-plugin`, `unshare --net`,
   `exec`s the worker.
6. Worker connects to the host's UDS socket, answers health handshake.
7. From here the request-proxy / capability path is exactly Phase 3–4.

Prod Linux **not** provisioned → `select_spawn_hook()` returns `None` →
`_supervisor_factory` raises `SandboxHardeningUnavailable` → `_enable_external`
logs + audits + returns `False`. The plugin stays disabled; bundled plugins and
the rest of the app are unaffected.

Dev / Windows → `select_spawn_hook()` returns `_default_spawn` → identical to
today.

## Error Handling

| Condition | Behavior |
|---|---|
| Prod Linux, user/wrapper missing | Fail closed: `_enable_external` → False, ERROR log, audit `plugin_sandbox_hardening_unavailable`. No spawn. |
| Wrapper arg validation fails | Wrapper exits 64–67; spawn/handshake fails; supervisor's existing restart-budget → auto-disable path runs. |
| `sudo -n` denied (sudoers missing) | Non-zero exit; same as above; surfaced in logs. |
| `disable_plugin` and `stop()` raises | Fix-A: `_hard_kill()` in except, pop in finally — no orphan. |
| Dev/Windows | `_default_spawn`; no sudo, no wrapper, unchanged. |

## Testing

All unit tests run cross-platform (Windows dev box + CI) **without root** by
mocking the exec boundary; the real `setpriv`/`unshare` path is Linux-only and
covered by a CI/manual smoke note.

**`backend/tests/plugins/sandbox/test_spawn_hook.py` (NEW)**
- `select_spawn_hook()` matrix: dev→`_default_spawn`; Windows (`sys.platform`
  patched)→`_default_spawn`; prod+Linux+present (probes patched)→`hardened_spawn`;
  prod+Linux+missing→`None`.
- `scrub_env()`: given an `os.environ` seeded with `SECRET_KEY`,
  `VPN_ENCRYPTION_KEY`, `DATABASE_URL`, the result contains **none** of them and
  contains `PATH`.
- `hardened_spawn` builds `[sudo, -n, WRAPPER, *argv]` and calls
  `create_subprocess_exec` with the scrubbed env (exec mocked).

**`backend/tests/plugins/test_manager_sandbox_failclosed.py` (NEW)**
- `select_spawn_hook` patched to `None` + `_hardening_required()` True →
  `_enable_external` returns `False` and writes the audit event; no supervisor
  stored.
- Hardening not required (dev) + `None` → supervisor built with default spawn,
  enable succeeds (existing Phase-4 behavior preserved).

**`backend/tests/plugins/test_manager_disable_orphan.py` (NEW — Fix-A)**
- A fake supervisor whose `stop()` raises → `disable_plugin` calls `_hard_kill()`,
  pops the entry, returns True; assert `_hard_kill` was awaited and `_sandboxes`
  no longer contains the name.

**`backend/tests/plugins/sandbox/test_spawn_wrapper.sh` (NEW — Linux CI, Windows-skip)**
- Drive the wrapper with `setpriv`/`unshare`/`exec` shimmed to `echo` on `PATH`:
  - rejects `--plugin-name "../evil"` (exit 64),
  - rejects `--plugin-dir` outside `/var/lib/baluhost/plugins` (exit 66),
  - rejects `--connect 'a;b'` (exit 67),
  - on valid input, the final exec line targets `setpriv … unshare --net …
    <python> -m app.plugins.sandbox.worker` with the canonicalized dir.
- Marked to run only where `bash` + the coreutils exist; the pytest suite skips
  it on Windows.

**Verification (no new code):** confirm Follow-up B — a unit test that makes
`_spawn_and_connect` fail the handshake asserts `start()` raised and the child
was hard-killed (mostly already covered by Phase-2b tests; extend if a gap).

## Deployment & Rollout

- `deploy/install/` changes provision the user, wrapper, and sudoers on the next
  full install/deploy run. The wrapper + sudoers are CODEOWNERS-flagged
  (`/deploy/`), so the CI-CD reviewer checklist applies (sudoers scoped to an
  exact binary; wrapper validates user-controlled args; no `ALL`, no globs).
- Until the prod box is re-provisioned, `select_spawn_hook()` returns `None` and
  external plugins fail closed. Because 0 external plugins are deployed, there is
  no functional regression — only a guarantee that none can run unhardened.
- Document one manual smoke on BaluNode after deploy: enable a throwaway external
  fixture plugin, confirm the worker runs as `baluhost-plugin`
  (`ps -o user= -p <pid>`), has no network (`nsenter`/`ip addr` shows only
  loopback in its netns), and cannot read `.env.production`.

## Security Review Notes

- **No new secret surface.** Env-scrubbing *removes* a secret-leak surface that
  exists today (full env inheritance).
- **sudoers** grants exactly one fixed binary, no args; the binary is root-owned
  and validates everything the caller can influence. Maps to the CI-CD reviewer
  checklist "Sudoers / systemd" and "Deploy script" items.
- **No `shell=True`, no string interpolation into commands** in the Python hook;
  argv is a list and the wrapper uses `"$@"`/quoted vars, no `eval`.
- **Fail-closed default** means a misconfigured/half-provisioned box cannot
  silently run plugins unhardened.
- **Blast radius** of a container/namespace escape: lands as `baluhost-plugin`
  (no sudo, no storage, no secrets) on the host kernel — strictly less than the
  `ci-runner` model already accepted for CI.

## Self-Review

- **Spec coverage:** env-scrubbing, user-drop, netns, rlimits, fail-closed,
  dev/Windows unchanged, Fix-A, B-verify, deploy provisioning, sudoers, socket/FS
  model, tests — each has a component + a test or verification step.
- **Consistency:** `select_spawn_hook()` returns `SpawnHook | None`; the `None`
  case is handled in exactly one place (`_supervisor_factory` →
  `SandboxHardeningUnavailable` → `_enable_external`). `_default_spawn` stays the
  `SandboxSupervisor` default so the dev path needs no `spawn_hook` kwarg.
- **Scope:** Phase 5a is backend + deploy only; frontend stays in 5b. Single,
  testable deliverable.
- **No placeholders** beyond the rlimit *values* and the wrapper flag-parsing
  body, which the plan fills with concrete code.
