# Standalone TUI `.deb` Artifact — Design

**Date:** 2026-06-07
**Branch:** `feat/tui-companion-rebuild`
**Status:** Approved (design Q&A), pending implementation plans

## Purpose

Ship the BaluHost TUI as a **separate, downloadable Linux release artifact** — analogous to the Tauri Companion app — instead of it only existing as a console entry point inside the `baluhost-backend` Python package.

Concretely: a `.deb` package containing a self-contained `baluhost-tui` binary (PyInstaller-bundled CPython + Textual + httpx + click), built by a new CI workflow and attached to GitHub Releases.

## Current state

- **Companion (Tauri)** is a real separate artifact: `tauri-build.yml` (ubuntu-latest) builds `.deb` + `.AppImage`, uploads a dev artifact on `push: main` and attaches them to the Release on tag `v*`.
- **TUI** is **not** a separate artifact: it's only `baluhost-tui = baluhost_tui.main:cli` inside the `baluhost-backend` package, present only where the backend is deployed.
- **Key enabler (from the rebuild, Plans 1–5):** the *interactive* TUI is already free of backend (`app.*`) imports — `import baluhost_tui.app` pulls **zero** `app.*` modules (verified). The only remaining `app.*` coupling is in three legacy CLI escape-hatches:
  - `commands/emergency.py` (`reset-password`) — direct DB (`app.core.database`, `app.models.user`).
  - `commands/status.py`, `commands/users.py` (+ `context.py`) — hybrid local-DB/API.
  - `commands/files.py` is **already** `app.*`-free (uses httpx directly) — no change needed.

## Decisions (from design Q&A)

1. **In-repo, own artifact** (like the Tauri app) — the TUI stays in `backend/baluhost_tui/`; it gets its own build that produces a separate release artifact. Not a separate repo.
2. **Packaging: `.deb` only** (BaluNode is Debian 13). No AppImage, no bare-binary tarball.
3. **Architecture: x86_64 only** for now. arm64 deferred to GitHub issue **#197**.
4. **CLI escape-hatches:** port `status`/`users` to the API; remove `context.py`; move `reset-password` out of the TUI package to a backend-only script. Result: the `baluhost_tui` package becomes fully `app.*`-free and thus cleanly bundleable.

## Two phases

PyInstaller statically bundles everything reachable, so the TUI package must be `app.*`-free **before** packaging — otherwise the whole FastAPI backend gets dragged into the binary. Hence:

- **Phase A — make `baluhost_tui` fully `app.*`-free** (prerequisite).
- **Phase B — PyInstaller build + `.deb` + CI workflow.**

---

## Phase A — `app.*`-free TUI package

### A1. Port `status` + `users` CLI to the API

`commands/status.py` and `commands/users.py` are rewritten to use a `BackendClient` (UDS/TCP auto-detect, same as the interactive TUI) and the `api.*` wrappers, dropping `get_context` and all `app.*` imports.

- `users` → `api.users.list_users(client)` → render the table from the returned dicts.
- `status` → `GET /api/system/info` (system summary) via the client + `api.users.list_users` for the user counts; render the table.

**Design consequence (for review):** these endpoints require authentication (`get_current_user`/admin). The current local-mode CLI worked without a token (direct DB). After the port, the CLI needs a token, sourced in this precedence:
1. `--token` option,
2. `BALUHOST_TOKEN` env var,
3. the persisted token file (`config.load_token()`, `~/.baluhost/token`).

To make (3) useful, the interactive TUI's successful login persists its access token via the existing `config.save_token()` helper (and `config.clear_token()` on a failed/again login). Note: access tokens are short-lived (15 min), so the saved-token path is best-effort convenience; `--token`/env remains the reliable path for scripting. On a 401/missing token the CLI prints a clear "not authenticated — pass --token or BALUHOST_TOKEN, or run `baluhost-tui dashboard` to log in" message.

(Open question surfaced for the user in review: `status`/`users` now overlap with the interactive TUI's Dashboard/Users screens and require a token. Keep both as ported API CLIs, or drop them in favor of the interactive screens? Default in this spec: **keep + port**, per the design decision.)

### A2. Move `reset-password` to a backend-only script

`reset-password` genuinely needs direct DB access *when the backend/login is down* — it is an offline recovery tool that belongs with the backend install, not a standalone TUI binary (which on a backend-less box could not reach the DB anyway).

- Move the logic from `baluhost_tui/commands/emergency.py` to a backend script `backend/scripts/reset_password.py` (a small `argparse`/`click` entry that imports `app.core.database` + `app.services.users`).
- Remove the `reset-password` command from `baluhost_tui/main.py` and delete `baluhost_tui/commands/emergency.py`.
- Document the new invocation (run on the server where the backend is installed): `python scripts/reset_password.py <username>` (or wire a `baluhost-reset-password` console script under the backend package — decided in the plan).

### A3. Delete `context.py`

After A1, the only importers of `baluhost_tui/context.py` are gone (`raid.py` dropped it in Plan 5; `status.py`/`users.py` in A1). Delete `context.py`.

### A4. Verify `app.*`-free

`python -c "import baluhost_tui.main, baluhost_tui.app, ...; <scan sys.modules>"` shows **no** `app.*` module loaded, and a source scan finds **no** `from app` / `import app` anywhere under `baluhost_tui/`.

---

## Phase B — PyInstaller `.deb` + CI

### B1. PyInstaller build

- A PyInstaller spec (or command) produces a one-file `baluhost-tui` executable from the `baluhost_tui` package entry (`baluhost_tui.main:cli`).
- Textual ships CSS/asset files that PyInstaller's static analysis misses — bundle them via `--collect-all textual` (and `--collect-all rich` if needed). Validate the binary actually launches (`baluhost-tui --help`) in CI.
- Target: linux x86_64 (build host = ubuntu-latest, which is x86_64).

### B2. `.deb` packaging

- Wrap the PyInstaller binary into a Debian package: binary installed to `/usr/bin/baluhost-tui`, minimal `control` (package `baluhost-tui`, version from the tag/`pyproject`, arch `amd64`, maintainer, short description, depends: essentially none since the binary is self-contained — possibly `libc6`).
- Tooling: build the `.deb` with `dpkg-deb --build` from a staged tree (simplest, no extra deps), or `fpm` (heavier). Plan picks `dpkg-deb` for minimal CI deps.

### B3. CI workflow `tui-build.yml`

Mirrors `tauri-build.yml` and obeys the CI-security rules (GitHub-hosted `ubuntu-latest`, **never** self-hosted — Layer 2):

- Triggers: `push: main`, tags `v*`, `workflow_dispatch`.
- Steps: checkout → setup Python 3.11 → `pip install` the TUI's runtime deps (textual/httpx/click) + pyinstaller → build binary → smoke `baluhost-tui --help` → stage + `dpkg-deb --build` → produce `baluhost-tui_<version>_amd64.deb`.
- `push: main` → upload `baluhost-tui-dev` artifact (retention ~14 days).
- tag `v*` → attach the `.deb` to the Release via `softprops/action-gh-release@v2` (same as the Tauri workflow).

### B4. Governance

- Per CI-security Layer 1, add the new paths to `.github/CODEOWNERS` → `@Xveyn`: `/.github/workflows/tui-build.yml` and the TUI packaging files (e.g. `/backend/baluhost_tui/packaging/` if a spec/control template lives there).
- Update `.claude/rules/ci-cd-security.md` Layer 2 table with the new `tui-build.yml` row (ubuntu-latest, push:main + tag + dispatch).

---

## Out of scope

- **arm64** build → issue **#197**.
- **AppImage / bare-binary** distribution (decision: `.deb` only).
- Separate-repo extraction (decision: in-repo).
- Any change to the interactive TUI's behavior (it's already `app.*`-free and shipped in Plans 1–5).

## Risks / trade-offs

1. **PyInstaller + Textual asset bundling** — Textual's CSS/widgets must be collected (`--collect-all textual`); a missing asset only shows at runtime. Mitigation: CI smoke-runs `baluhost-tui --help` and a non-interactive code path.
2. **CLI auth friction** — ported `status`/`users` need a token (was token-free in local-DB mode). Mitigated by `--token`/env/saved-token; surfaced for user review.
3. **Binary size** — a PyInstaller bundle with CPython + Textual is ~30–60 MB. Acceptable for a `.deb`.
4. **`reset-password` relocation** — moving it out of the TUI is a (documented) change to the recovery workflow; it stays available wherever the backend is installed.
5. **Version source** — the `.deb` version derives from the git tag on release (`v<version>`); for `push: main` dev builds, derive from `pyproject` version + short SHA.

## Implementation plans (to be written)

- **Plan A (cleanup):** A1–A4 — port `status`/`users`, move `reset-password`, delete `context.py`, verify `app.*`-free.
- **Plan B (packaging):** B1–B4 — PyInstaller spec, `.deb` build, `tui-build.yml`, CODEOWNERS + ci-cd-security rule.
