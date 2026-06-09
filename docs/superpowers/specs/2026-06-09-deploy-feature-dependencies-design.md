# Design: Optional Feature Modules & Dependency Documentation (Issue #182)

**Date:** 2026-06-09
**Issue:** #182 — `docs(deploy): Feature-Systemabhängigkeiten & Debian-only-Gate nicht installiert/dokumentiert`
**Branch:** `docs/deploy-dependencies-182`
**Scope:** Full solution — central dependency documentation **+** optional interactive feature installation in the installer.

---

## Problem

Two coupled onboarding gaps in the production setup:

1. **Hard Debian-12/13 lock.** `deploy/install/modules/01-preflight.sh:16` aborts on any other OS. Not prominently documented anywhere.
2. **Feature system dependencies are neither installed nor centrally documented.** The installer (`modules/02-system-packages.sh`) installs only the core base (postgresql, nginx, python, node, git, build-essential, curl, lsb-release). Missing: `mdadm` (RAID), `smartmontools` (SMART), `wireguard-tools` (VPN), `samba` (SMB), `nfs-kernel-server` (NFS), `rclone` (Cloud), `wsdd` (WS-Discovery), `avahi` (mDNS). These features degrade silently or require manual `apt install` plus scattered `deploy/scripts/*` scripts. There is no single dependency/requirements document.

### Current state (verified)

| Feature | Package(s) | Currently installed by | Status |
|---|---|---|---|
| Core NAS | postgresql(-contrib), nginx, python3-venv/dev/pip, nodejs, npm, git, build-essential, curl, lsb-release | `modules/02-system-packages.sh` | ✅ in installer |
| RAID | `mdadm` | — nothing — | ❌ dark |
| SMART | `smartmontools` | — nothing — | ❌ dark |
| VPN | `wireguard-tools` | `scripts/setup-wireguard.sh` **configures only** (assumes `wg`/`wg-quick` present) | ❌ dark |
| Cloud | `rclone` | — nothing — | ❌ dark |
| Samba/SMB | `samba`, `samba-common-bin` | `deploy/samba/setup-samba.sh` (manual, not wired) | ⚠️ manual |
| NFS | `nfs-kernel-server` | `deploy/nfs/setup-nfs.sh` (manual, not wired) | ⚠️ manual |
| WS-Discovery | `wsdd2`/`wsdd` | `deploy/wsdd/setup-wsdd.sh` (manual, not wired) | ⚠️ manual |
| mDNS | `avahi-daemon`, `avahi-utils` | `scripts/install-avahi.sh` (manual, not wired) | ⚠️ manual |

The 13-module installer chain (`install.sh`) wires **none** of the feature scripts. Hardware sudoers (RAID/SMART, via `install-hardware-sudoers.sh`) are likewise not pulled by the installer chain — only module 13 installs the *power* sudoers.

---

## Goals

- Provide a single source of truth: a Feature → Packages → Setup-script dependency matrix.
- Let the installer optionally install and fully configure each feature (interactive prompt + config flags).
- Preserve the exact current behavior of existing automated (`--non-interactive`) installs: no opt-in ⇒ no optional feature installed.
- Document the Debian-only restriction and *why* it exists.

## Non-Goals (YAGNI)

- Opening the preflight gate to other distros (Ubuntu/Fedora/Arch/RHEL).
- Package-name mapping for non-Debian distros.
- Automatic hardware-based feature auto-detection.

---

## Architecture (Approach A — chosen)

A new installer module driven by a declarative feature catalog. The module chain 01–13 stays untouched; a new module 14 reads `ENABLE_*` flags and runs each enabled feature's full setup by invoking the **existing** scripts with the configured service user. The same catalog feeds the documentation matrix.

### Files

**New:**
- `deploy/install/lib/features.sh` — declarative feature catalog + `run_feature()` dispatcher. Per feature: `key`, `label`, `packages`, `setup_fn`, `precheck_fn`.
- `deploy/install/modules/14-optional-features.sh` — iterates the catalog, skips features whose `ENABLE_<KEY>` is not `true`, installs packages (`apt-get install`), runs the setup action idempotently, collects per-feature results into an end-of-module report.
- `deploy/install/verify/test-features.sh` — offline (no-root) harness that sources `features.sh` and asserts the selection/dispatch logic with mocked `apt-get`/setup functions.
- `docs/deployment/FEATURE_DEPENDENCIES.de.md` + `.en.md` — central matrix + activation guide + Debian-only explanation.

**Changed:**
- `deploy/install/lib/config.sh` — add `ENABLE_RAID/SMART/VPN/CLOUD/SAMBA/NFS/WSDD/MDNS` defaults (`false`); write them in `save_config()`.
- `deploy/install/install.sh` — add `14-optional-features` to `MODULES`; add an "Optional Features" block to `gather_input()` (interactive only) using `confirm()` per feature.
- `README.md` + `docs/deployment/DEPLOYMENT.{de,en}.md` — short "Supported OS: Debian 12/13 only" note + link to the new doc (reference only, no content duplication).

---

## Feature Catalog

Each catalog entry maps to an `ENABLE_<KEY>` flag. Setup actions invoke existing scripts with the configured user — no logic duplication.

| Key | Packages | Setup action (after package install) | Precheck (warn only, never abort) |
|---|---|---|---|
| `RAID` | `mdadm` | `install-hardware-sudoers.sh` (idempotent, visudo-validated) | arrays present in `/proc/mdstat`? |
| `SMART` | `smartmontools` | `install-hardware-sudoers.sh` (shared sudoers; run **once** for RAID∪SMART) | real disks via `lsblk`? |
| `VPN` | `wireguard-tools` | `scripts/setup-wireguard.sh "$BALUHOST_USER"` | WireGuard kernel module? |
| `CLOUD` | `rclone` | — (runs as service user, no sudoers) | — |
| `SAMBA` | (script installs its own) | `SERVICE_USER=$BALUHOST_USER STORAGE_GROUP=$BALUHOST_GROUP samba/setup-samba.sh` | — |
| `NFS` | (script installs its own) | `SERVICE_USER=$BALUHOST_USER STORAGE_GROUP=$BALUHOST_GROUP nfs/setup-nfs.sh` | — |
| `WSDD` | (script installs its own) | `wsdd/setup-wsdd.sh` | — |
| `MDNS` | (script installs its own) | `scripts/install-avahi.sh` | — |

### Key rules

- **Shared hardware sudoers.** RAID and SMART share `/etc/sudoers.d/baluhost-hardware`. The dispatcher runs `install-hardware-sudoers.sh` **exactly once** when RAID *or* SMART is enabled (a guard variable), never twice.
- **Service-user propagation.** `samba`/`nfs` setup scripts read `SERVICE_USER`/`STORAGE_GROUP` from env (today's defaults `sven`/`baluhost`); module 14 overrides them explicitly with the configured `BALUHOST_USER`/`BALUHOST_GROUP`. `setup-wireguard.sh` takes the user as `$1`. `install-hardware-sudoers.sh` reads `BALUHOST_USER` from env.
- **Idempotency.** All target scripts are re-run-safe (sudoers validated via `visudo -cf` before replacing the live file; configs backed up with a timestamp; `apt-get install` is a no-op when the package is present). Module 14 is therefore itself idempotent and can be re-run standalone via `sudo ./install.sh --module 14-optional-features`.
- **Error policy.** A single feature setup failure is reported (`log_error` + end-of-module summary) but does **not** abort the installer (the core NAS is already running). The module returns non-zero if at least one *selected* feature failed, so CI/automation can detect it.
- **Precheck policy.** Precheck findings are warnings only (e.g. "RAID selected but no arrays in /proc/mdstat" → still install; the package is harmless).

---

## Non-interactive behavior

- Features are chosen exclusively via `ENABLE_<KEY>=true` flags in `/etc/baluhost/install.conf`.
- **Default when unset = none.** No optional feature is installed — exactly today's behavior. Existing automated installs are unaffected.
- Interactive mode: `gather_input()` asks `confirm()` per feature; answers are persisted to the config by the existing `save_config()` flow before the modules run.

---

## Documentation deliverable

`docs/deployment/FEATURE_DEPENDENCIES.{de,en}.md` (bilingual, content-identical):

1. **Dependency matrix** — same table as the catalog (Feature → Packages → Setup script/action → status after a default install). Explicitly distinguishes what runs after `install.sh` *without* feature selection (core) vs. what stays dark until enabled.
2. **Activation — two paths:** interactive prompt; or `ENABLE_<KEY>=true` in `install.conf` + `sudo ./install.sh --module 14-optional-features`.
3. **Per-feature block** — what it unlocks, which backend service consumes it, and the manual alternative (running the standalone script directly).
4. **Debian-only explanation** — *why* (preflight `01-preflight.sh:16`; tested only on bookworm/trixie; apt package names; systemd assumptions). Clear statement that other distros are unsupported; notes that `install-avahi.sh` is multi-distro but the rest is not — no "half-portable" promise.

`README.md` + `DEPLOYMENT.{de,en}.md`: one short "Supported OS: Debian 12/13 only" section each + a link to the new doc. Reference only; the new doc is the single source.

---

## Testing & Verification

1. **Static (local, CI-friendly):**
   - `bash -n` syntax check on all changed/new scripts.
   - `shellcheck` (if available) on `features.sh` + `14-optional-features.sh`.
   - `install.sh --list-modules` lists `14-optional-features`.

2. **Offline dispatcher test (`deploy/install/verify/test-features.sh`, no root):** sources `features.sh` and tests the selection logic with mocked `apt-get`/setup functions (PATH stub or function override). Assertions:
   - `ENABLE_*=false` ⇒ feature skipped (no apt call).
   - `ENABLE_RAID=true` + `ENABLE_SMART=true` ⇒ `install-hardware-sudoers.sh` invoked **exactly once** (single-run guard).
   - User propagation: mocked `setup-samba.sh` sees `SERVICE_USER=$BALUHOST_USER`.
   - A feature failure ⇒ module returns non-zero, but the loop continues for the others.

3. **Real (on the box, manual):** `sudo ./install.sh --module 14-optional-features` with flags set — the authoritative validation, documented as a verification step in the new doc.

No changes to the pytest/vitest suites (deploy/docs only, no app code).

---

## Out of scope / follow-ups

- Opening preflight to other distros (would require package-name mapping + systemd-unit review) — only flagged, not done here.
- Wiring `install-hardware-sudoers.sh` into the *default* install chain independent of RAID/SMART selection — out of scope; this design only triggers it when RAID/SMART is opted in.
