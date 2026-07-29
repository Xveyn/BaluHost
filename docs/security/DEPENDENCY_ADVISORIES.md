# Advisory Register: findings we deliberately do not fix

Reasoning for Dependabot and Code Scanning findings that are **intentionally** not
closed by an upgrade — because they do not apply to us, because the fix costs more
than the risk, or because it is blocked on something external.

## What this file is — and what it is not

GitHub holds the **state** (open / dismissed / fixed). This file holds the
**reasoning**. Keeping them apart has a concrete cause: Dependabot's
`dismissed_comment` field is capped at **280 characters**. A justification that
cites `file:line` and states the condition under which it expires does not fit
there. In the UI it is also not diffable, never shows up in a review, and is gone
the moment an alert is reopened.

**This is not a second source of truth about state.** Whether an alert is open is
recorded in GitHub, not here. If this file and GitHub disagree, GitHub wins and
the entry below is the thing that needs fixing.

## The rule that keeps this register from rotting

> **Every entry needs a re-evaluation condition.**

That is, a checkable sentence describing when the decision *stops being valid*.
"Does not affect us" without that condition is not a finding — it is an excuse
with unlimited shelf life, and exactly the kind of note nobody dares touch three
years later.

An entry without a re-evaluation condition is incomplete and should be rejected in
review.

## Status values

| Status | Meaning |
|---|---|
| `not applicable` | The vulnerable code path does not exist here. Dismissed in GitHub as `not_used`. |
| `deferred` | It does affect us, but the fix is disproportionately expensive. Stays open and visible. |
| `blocked` | The fix is wanted but currently fails on something external (toolchain, major upgrade). |

---

## GHSA-qwww-vcr4-c8h2 — React Router: RSC Mode CSRF Bypass

| | |
|---|---|
| **Status** | `not applicable` |
| **Decided** | 2026-07-29 |
| **Package** | `react-router` (transitively via `react-router-dom`) |
| **Affected** | `>= 7.12.0, < 8.3.0` — we run 7.18.2 |
| **Alert** | Dependabot #76, dismissed as `not_used` |

**Why we are not affected.** The advisory describes a CSRF bypass in React
Router's **RSC mode**. BaluHost is a pure client-side SPA:

- `client/src/App.tsx:1` imports `BrowserRouter` from `react-router-dom` — the
  declarative client router, not a data router and not framework mode
- not a single `@react-router/*` server package is installed (neither
  `@react-router/serve` nor `@react-router/express`)
- no SSR, no RSC — the build is a static Vite bundle served by Nginx

The vulnerable code path is therefore never reached.

**What the fix would cost.** React Router **8.3.0** — a major. For an advisory
covering a mode we do not run, that is the wrong trade: major-upgrade risk for
zero benefit.

> **Re-evaluation condition.** This assessment falls as soon as **any** of the
> following becomes true:
> 1. a `@react-router/*` package appears in `client/package.json`,
> 2. `client/src/App.tsx` moves from `BrowserRouter` to `createBrowserRouter` with
>    framework/RSC mode, or
> 3. the frontend gains server-side rendering at all.
>
> At that point the alert must be reassessed and the major becomes due.

---

## brace-expansion — DoS via unbounded expansion (OOM)

| | |
|---|---|
| **Status** | `deferred` |
| **Decided** | 2026-07-29 |
| **Package** | `brace-expansion`, transitively via `minimatch` → `eslint` / `typescript-eslint` |
| **Affected** | `<= 5.0.7` — that is **every** released version, including the newest |
| **Source** | `npm audit` only, no GitHub alert |

**Why deferred.** The advisory has no patched version yet: the range covers
everything up to and including the current 5.0.7. npm's only resolution path is
`eslint@10.x` — a major bump of the entire lint toolchain.

Exposure is low: `brace-expansion` runs at lint time only, over glob patterns
**we** write in the ESLint configuration. It processes no user input and is never
shipped.

**What the fix would cost.** ESLint 9 → 10 with configuration work, against a CI
gate that requires `eslint .` to report **0 errors**. That is a PR of its own with
real effort — not part of a dependency bundle.

> **Re-evaluation condition.** As soon as `brace-expansion` ships a patched
> version reachable within our existing ranges, this becomes an ordinary bump.
> Independently of that, it falls due whenever ESLint 10 is on the table for other
> reasons — then this gets fixed as a side effect.

---

## quinn-proto / glib — Tauri companion (Cargo)

| | |
|---|---|
| **Status** | `blocked` |
| **Recorded** | 2026-07-29 |
| **Package** | `quinn-proto` 0.11.14 → 0.11.15, `glib` 0.18.5 → 0.20.0 |
| **Location** | `client/src-tauri/Cargo.lock` |
| **Alerts** | Dependabot, open |

**Why still open.** Two unrelated reasons that happen to share a lockfile:

- **`quinn-proto`** would be a plain patch (0.11.14 → 0.11.15) and is
  uncontroversial. It fails only because the development machine has no Rust
  toolchain installed — a `Cargo.lock` can be neither generated cleanly nor
  verified without `cargo`.
- **`glib`** is a different matter: 0.18.5 → 0.20.0 is **two majors**, and the
  version is tied to Tauri's own GTK dependencies. Realistically that is not a
  lockfile bump but a Tauri upgrade.

Both affect only the companion app — not the web frontend and not the backend.

> **Re-evaluation condition.** `quinn-proto` falls as soon as anyone with a Rust
> toolchain (or a CI job based on `tauri-build.yml`) can run the bump. `glib`
> falls together with the next Tauri upgrade — do not touch it separately before
> then.

---

## Adding an entry

1. Dismiss the finding in GitHub (where applicable) with a **short** justification
   and a pointer to this file — 280 characters is the limit.
2. Add a section here following the pattern above: identifier as the heading, the
   status table, the reasoning with **references into the code**
   (`file.ts:line`), and what the fix would cost.
3. Write the re-evaluation condition. Without it the entry is not finished.
4. If a finding does get fixed later, **delete** its section rather than rewriting
   it — the history lives in the git log, and a register that also collects closed
   cases becomes unreadable.

## Note on language and file layout

The rest of `docs/security/` ships `.de.md`/`.en.md` pairs. This file is
deliberately a single English file: it is appended to on every dismissal, and an
entry that lands in only one of two language versions would be worse than a
monolingual file — for a security register, divergence is the expensive failure
mode.
