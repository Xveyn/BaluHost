# TUI `.deb` Packaging + CI (Plan B of standalone-.deb) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the (now `app.*`-free) `baluhost_tui` into a standalone Linux `.deb` via PyInstaller, produced by a new `tui-build.yml` workflow that uploads a dev artifact on `push: main` and attaches the `.deb` to the GitHub Release on tag `v*` — mirroring `tauri-build.yml`.

**Architecture:** A small entry script feeds PyInstaller, which produces a one-file `baluhost-tui` binary (bundled CPython + Textual + Rich + Click). A `build_deb.sh` stages the binary into `/usr/bin/baluhost-tui` with a Debian `control` file and runs `dpkg-deb --build`. The `tui-build.yml` workflow runs both on `ubuntu-latest` (per CI-security Layer 2 — GitHub-hosted, never self-hosted). CODEOWNERS and the ci-cd-security rule are updated.

**Tech Stack:** Python 3.11, PyInstaller, `dpkg-deb`, GitHub Actions. Builds on Plan A (the `app.*`-free TUI package). Spec: `docs/superpowers/specs/2026-06-07-tui-standalone-deb-artifact-design.md`.

---

## IMPORTANT: how this plan is verified

PyInstaller builds an OS-native binary — a Linux `.deb` can **only** be produced on Linux (the CI `ubuntu-latest` runner), **not** on the Windows dev machine. So this plan is **not** locally TDD-able the way the Python plans were. Verification per task is limited to what's checkable on any OS:
- Python files: `python -m py_compile` / `ast.parse`.
- Shell script: `bash -n` (syntax) + shellcheck-style review.
- YAML workflow: parse with `python -c "import yaml; yaml.safe_load(...)"` (PyYAML is already a dev/runtime dep transitively; if missing, use a JSON-ish structural read).
- The **real** verification is the first CI run on `push: main` producing `baluhost-tui-dev`, plus a documented manual smoke on the Debian box (Task 6). The implementer must NOT claim the binary/`.deb` "works" without that CI run — only that the files are syntactically valid and structurally correct.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/packaging/tui/entry.py` | Create | PyInstaller entry: `from baluhost_tui.main import cli; cli()` |
| `backend/packaging/tui/build_deb.sh` | Create | stage binary + `control` → `dpkg-deb --build` |
| `.github/workflows/tui-build.yml` | Create | PyInstaller build + `.deb` + artifact/release upload |
| `.github/CODEOWNERS` | Modify | own the new workflow + packaging path |
| `.claude/rules/ci-cd-security.md` | Modify | add `tui-build.yml` to the Layer 2 runner/trigger table |

Out of scope: arm64 (issue #197); AppImage; any interactive-TUI change.

---

## Task 1: PyInstaller entry script

**Files:**
- Create: `backend/packaging/tui/entry.py`

- [ ] **Step 1: Create the entry script**

Create `backend/packaging/tui/entry.py`:

```python
"""PyInstaller entry point for the standalone `baluhost-tui` binary.

PyInstaller bundles this module; it just hands off to the Click CLI. The
`baluhost_tui` package must be importable at build time (the workflow passes
`--paths .` from `backend/`).
"""
from baluhost_tui.main import cli

if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: Validate it compiles**

Run: `cd backend ; python -m py_compile packaging/tui/entry.py ; if ($?) { Write-Output "compiles" }`
Expected: `compiles`.

- [ ] **Step 3: Validate it imports the CLI (the package is `app.*`-free, so this works without the backend installed)**

Run: `cd backend ; python -c "import runpy, importlib; m=importlib.import_module('baluhost_tui.main'); print('cli' , hasattr(m,'cli'))"`
Expected: `cli True`.

- [ ] **Step 4: Commit**

```
git add backend/packaging/tui/entry.py
git commit -m "feat(tui): PyInstaller entry script for standalone binary"
```

---

## Task 2: `.deb` build script

**Files:**
- Create: `backend/packaging/tui/build_deb.sh`

- [ ] **Step 1: Create the build script**

Create `backend/packaging/tui/build_deb.sh`:

```bash
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
```

(Maintainer line uses a noreply address — adjust if a real contact is preferred. `--root-owner-group` makes the package contents root-owned without needing fakeroot.)

- [ ] **Step 2: Validate shell syntax**

Run (the Bash tool runs bash): `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild/backend" && bash -n packaging/tui/build_deb.sh && echo "syntax OK"`
Expected: `syntax OK`.

- [ ] **Step 3: Validate the arg-guard path (no binary → clean error, exit 1)**

Run: `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild/backend" && bash packaging/tui/build_deb.sh 1.0.0 /no/such/binary out 2>&1; echo "exit=$?"`
Expected: prints `error: binary not found: /no/such/binary` and `exit=1`. (We can't run the full `dpkg-deb` path on Windows/without a binary — that's exercised in CI.)

- [ ] **Step 4: Commit**

```
git add backend/packaging/tui/build_deb.sh
git commit -m "feat(tui): dpkg-deb packaging script for standalone binary"
```

---

## Task 3: `tui-build.yml` workflow

**Files:**
- Create: `.github/workflows/tui-build.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/tui-build.yml`:

```yaml
name: TUI Build

on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_dispatch:

jobs:
  build:
    # MUST stay on a GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for releasable / PR-touched build paths).
    runs-on: ubuntu-latest
    permissions:
      contents: write  # required for tag-triggered release uploads
    steps:
      - uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install build deps
        # The TUI package is app.*-free, so only its runtime deps + pyinstaller.
        run: pip install pyinstaller textual httpx click rich

      - name: Compute version
        id: ver
        run: |
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
          else
            echo "version=0.0.0+$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
          fi

      - name: Build one-file binary
        working-directory: backend
        run: >-
          pyinstaller --onefile --name baluhost-tui
          --paths .
          --collect-all textual
          --collect-all rich
          --collect-all click
          packaging/tui/entry.py

      - name: Smoke test binary
        run: backend/dist/baluhost-tui --help

      - name: Build .deb
        run: bash backend/packaging/tui/build_deb.sh "${{ steps.ver.outputs.version }}" backend/dist/baluhost-tui dist

      - name: Upload artifact (push to main)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/upload-artifact@v6
        with:
          name: baluhost-tui-dev
          path: dist/*.deb
          retention-days: 14

      - name: Upload to release (tag)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*.deb
```

- [ ] **Step 2: Validate the YAML parses**

Run: `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild" && python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/tui-build.yml',encoding='utf-8')); print('jobs:', list(d['jobs'])); print('runner:', d['jobs']['build']['runs-on']); print('triggers:', list(d['on']))"`
Expected: `jobs: ['build']`, `runner: ubuntu-latest`, `triggers: ['push', 'tags'...]` (the `on:` keys — `push` and `workflow_dispatch`). If PyYAML is not installed, `pip install pyyaml` first.

- [ ] **Step 3: Confirm runner is GitHub-hosted (CI-security Layer 2)**

Read the file and confirm `runs-on: ubuntu-latest` (NOT `self-hosted`). This is a hard requirement — a self-hosted runner here would violate the trust model.

- [ ] **Step 4: Commit**

```
git add .github/workflows/tui-build.yml
git commit -m "ci(tui): tui-build.yml — PyInstaller .deb on ubuntu-latest, attach to release"
```

---

## Task 4: Governance — CODEOWNERS + ci-cd-security rule

**Files:**
- Modify: `.github/CODEOWNERS`
- Modify: `.claude/rules/ci-cd-security.md`

- [ ] **Step 1: Add the new paths to CODEOWNERS**

In `.github/CODEOWNERS`, replace:

```
# CI/CD workflow definitions
/.github/workflows/  @Xveyn
/.github/CODEOWNERS  @Xveyn
/.github/workflows/tauri-build.yml @Xveyn
```

with:

```
# CI/CD workflow definitions
/.github/workflows/  @Xveyn
/.github/CODEOWNERS  @Xveyn
/.github/workflows/tauri-build.yml @Xveyn
/.github/workflows/tui-build.yml @Xveyn

# Standalone TUI packaging (PyInstaller entry + .deb build)
/backend/packaging/tui/ @Xveyn
```

- [ ] **Step 2: Add the workflow to the ci-cd-security Layer 2 table**

In `.claude/rules/ci-cd-security.md`, find the Layer 2 runner/trigger table row for `tauri-build.yml`:

```
| `tauri-build.yml` | `ubuntu-latest` | `push: main`, tag, `workflow_dispatch` |
```

Add a new row immediately after it:

```
| `tui-build.yml` | `ubuntu-latest` | `push: main`, tag, `workflow_dispatch` |
```

- [ ] **Step 3: Verify the edits landed**

Run: `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild" && python -c "import pathlib; co=pathlib.Path('.github/CODEOWNERS').read_text(encoding='utf-8'); r=pathlib.Path('.claude/rules/ci-cd-security.md').read_text(encoding='utf-8'); print('CODEOWNERS tui:', 'tui-build.yml' in co and 'backend/packaging/tui' in co); print('rule tui:', 'tui-build.yml' in r)"`
Expected: both `True`.

- [ ] **Step 4: Commit**

```
git add .github/CODEOWNERS .claude/rules/ci-cd-security.md
git commit -m "ci(tui): own tui-build.yml + packaging in CODEOWNERS; document in ci-cd-security"
```

---

## Task 5: Local structural verification (no binary build)

**Files:** none changed.

- [ ] **Step 1: All new Python compiles**

Run: `cd backend ; python -m py_compile packaging/tui/entry.py ; if ($?) { Write-Output OK }`
Expected: `OK`.

- [ ] **Step 2: Shell script syntax**

Run: `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild/backend" && bash -n packaging/tui/build_deb.sh && echo OK`
Expected: `OK`.

- [ ] **Step 3: Workflow YAML parses + runner is GitHub-hosted**

Run: `cd "D:/Programme (x86)/Baluhost/.claude/worktrees/feat+tui-companion-rebuild" && python -c "import yaml; d=yaml.safe_load(open('.github/workflows/tui-build.yml',encoding='utf-8')); assert d['jobs']['build']['runs-on']=='ubuntu-latest'; print('runner OK')"`
Expected: `runner OK`.

- [ ] **Step 4: TUI test suite still green (no regression from packaging files)**

Run: `cd backend ; python -m pytest tests/tui/ --no-cov -q`
Expected: all pass (packaging files don't touch the package; this just confirms nothing broke).

---

## Task 6: CI + manual smoke verification (documented — runs in CI / on the Debian box)

**Files:** none changed. This task is the real end-to-end verification; it cannot run on the Windows dev machine.

- [ ] **Step 1: Trigger the workflow**

Push the branch (or merge to `main`) / run `workflow_dispatch`. Confirm `tui-build.yml` runs on `ubuntu-latest`, the `Smoke test binary` step prints the CLI help, and the `Build .deb` step prints `built dist/baluhost-tui_<version>_amd64.deb`. The `baluhost-tui-dev` artifact appears on the run.

- [ ] **Step 2: Manual smoke on Debian (BaluNode)**

Download the `.deb`, then on the Debian box:
```
sudo dpkg -i baluhost-tui_<version>_amd64.deb
baluhost-tui --help          # prints the command list
# with the backend running (local socket present):
baluhost-tui dashboard       # login admin, screens load over the UDS
```
Expected: the binary runs without a system Python; `dashboard` connects over `/run/baluhost/local.sock` (channel=local) and destructive ops work.

- [ ] **Step 3: Tag-release smoke (on the next release tag)**

On the next `v*` tag, confirm the `.deb` is attached to the GitHub Release alongside the Companion `.deb`/`.AppImage`.

---

## Self-Review

**1. Spec coverage (Phase B of the standalone-.deb spec):**
- B1 "PyInstaller build (collect textual)" → Tasks 1 + 3 (`--collect-all textual rich click`, `--paths .`). ✓
- B2 ".deb packaging (dpkg-deb, /usr/bin/baluhost-tui)" → Task 2. ✓
- B3 "tui-build.yml on ubuntu-latest; dev artifact on push:main; attach on tag v*" → Task 3. ✓
- B4 "CODEOWNERS + ci-cd-security Layer 2 row" → Task 4. ✓
- x86_64 only / no AppImage / arm64→#197 — honored (arch `amd64`, single `.deb`).

**2. Placeholder scan:** No TBD/TODO; every file is complete; every local-checkable step has an exact command + expected output; the un-checkable (binary/.deb) steps are explicitly isolated in Task 6 with documented expectations (not silent placeholders).

**3. Type/consistency checks:**
- Workflow `Build .deb` calls `build_deb.sh <version> backend/dist/baluhost-tui dist` — matches `build_deb.sh`'s `<version> <binary_path> [out_dir]` signature. ✓
- PyInstaller writes to `backend/dist/baluhost-tui` (`working-directory: backend`, `--onefile --name baluhost-tui`); the smoke step and `build_deb.sh` binary arg both reference `backend/dist/baluhost-tui`. ✓
- `entry.py` imports `baluhost_tui.main:cli` — exists and is `app.*`-free (Plan A). `--paths .` (= `backend/`) makes it importable at build time. ✓
- `.deb` filename `baluhost-tui_<version>_amd64.deb`; upload globs `dist/*.deb`. ✓

**4. Risks (carried from spec):**
- PyInstaller may miss a Textual asset → mitigated by `--collect-all textual` + the `--help` smoke (Task 6 Step 1) + a `dashboard` smoke (Task 6 Step 2). If `--help` works but `dashboard` crashes on a missing asset, add `--collect-all` for the offending package.
- Dev-build version `0.0.0+<sha>` — `+` is valid in Debian versions and filenames.
- This plan's correctness is only fully proven by the CI run (Task 6) — flagged up front.

---

## After this plan

The standalone TUI `.deb` pipeline is complete. Remaining TUI backlog (separate, later): form-based destructive ops (RAID create/format, users bulk-delete), new read screens (plugins/vpn/network/settings), `BaseScreen`, welcome-version/`sys.path` cleanup, arm64 (#197). And finally: open the PR for the whole `feat/tui-companion-rebuild` branch.
