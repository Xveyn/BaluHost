# ESLint CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a blocking `npx eslint .` step to the `frontend-build` CI job on a curated `eslint.config.js` that makes the current tree green, fixing the cheap high-value errors and staging the rest to follow-up issues.

**Architecture:** Curate `client/eslint.config.js` (noisy/unactionable rules → `warn`/`off`, Playwright e2e excluded from `react-hooks/*`, `_`-prefix ignore pattern for unused vars). Then fix the four rules that stay `error` — `prefer-const`, `no-empty`, `no-useless-catch`, `@typescript-eslint/no-unused-vars` — until `eslint .` reports 0 errors. Finally wire a blocking lint step into `.github/workflows/ci-check.yml`. No runtime behavior changes; the oracle is `npx eslint .` exit 0 plus a green build and Vitest run.

**Tech Stack:** ESLint 9 (flat config), typescript-eslint 8, eslint-plugin-react-hooks 7, eslint-plugin-react-refresh, GitHub Actions (`ubuntu-latest`).

**Spec:** `docs/superpowers/specs/2026-06-14-eslint-ci-gate-design.md`
**Issue:** #210. Follow-ups: #244 (PR B), #245 (`no-explicit-any`), #246 (React Compiler lints).

---

## Working directory & verification conventions

All `eslint`/`npm`/`vitest` commands run from `client/`:

```bash
cd "D:/Programme (x86)/Baluhost/client"
```

**The verification oracle** for every fix task is the ESLint summary line printed by:

```bash
npx eslint .
```

ESLint exits **0** even with warnings present (warnings are the intentional staged backlog). It exits **1** if any `error`-level problem remains. Expected error/warning totals are stated per task; the precise warning total may differ by a few — only the **error** total and the **named rule reaching 0** are load-bearing checkpoints.

The repo runs with `core.autocrlf=true` on Windows — when editing a file, preserve its existing line endings (Edit/Write tools handle this; do not bulk-reformat).

---

## Task 1: Curate `eslint.config.js`

**Files:**
- Modify: `client/eslint.config.js` (full rewrite of the exported config)

- [ ] **Step 1: Replace the config file contents**

Replace the entire contents of `client/eslint.config.js` with:

```js
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Build output — never lint generated bundles (dist = desktop, dist-pi = Pi build).
  globalIgnores(['dist', 'dist-pi']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // --- Staged ESLint hardening (#210, Stufe 2 von #184) ---
      // This gate is BLOCKING. The rules below are deliberately relaxed so the
      // current tree is green; each is ramped back to `error` in a dedicated
      // follow-up PR. Do NOT silence freshly-introduced errors by adding rules
      // here without discussion — see the linked issues.

      // #245 — 164 violations, real typing work across 100+ files. Kept visible as warn.
      '@typescript-eslint/no-explicit-any': 'warn',
      // #244 — risky to auto-fix (effect deps → infinite-loop risk). Stays warn.
      'react-hooks/exhaustive-deps': 'warn',
      // #244 — Fast-Refresh hygiene; ramped to error in the same follow-up.
      // Preserve allowConstantExport from reactRefresh.configs.vite so a bare
      // severity override doesn't re-introduce constant-export warnings.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // #246 — React Compiler lints (react-hooks v7 "recommended"). Not actionable
      // without a deliberate React Compiler migration; set to off so they don't
      // bury the actionable exhaustive-deps warnings. Reactivated in the migration PR.
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/static-components': 'off',

      // Enforced from day one. A leading `_` marks an intentionally-unused binding.
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
    },
  },
  {
    // Playwright e2e tests are not React. The react-hooks plugin misreads
    // Playwright's `use(...)` fixture callback as the React `use` hook
    // (rules-of-hooks false positives, see #210). Disable hook rules here.
    files: ['tests/e2e/**'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
      'react-hooks/exhaustive-deps': 'off',
    },
  },
])
```

- [ ] **Step 2: Run ESLint and confirm the curated baseline**

Run:
```bash
npx eslint .
```
Expected: exit code **1** (errors still present — we fix them next), summary near **43 errors, ~230 warnings**. Crucially, the only **error**-level rules remaining must be: `prefer-const`, `no-empty`, `@typescript-eslint/no-unused-vars`, `no-useless-catch`. There must be **no** `react-hooks/rules-of-hooks` errors and **no** React-Compiler-lint errors. `@typescript-eslint/no-explicit-any`, `react-hooks/exhaustive-deps`, and `react-refresh/only-export-components` must now appear as **warnings**.

If any other rule still reports an error, stop and re-check the config before continuing.

- [ ] **Step 3: Commit**

```bash
git add client/eslint.config.js
git commit -m "ci(lint): curate eslint.config.js for staged gate (#210)"
```

---

## Task 2: Fix `prefer-const` (1 site)

**Files:**
- Modify: `client/src/pages/AdminDatabase.tsx:161`

- [ ] **Step 1: Apply the fix**

At `client/src/pages/AdminDatabase.tsx:161`, `mounted` is never reassigned (that is why `prefer-const` fires). Change:

```ts
    let mounted = true
```
to:
```ts
    const mounted = true
```

(Behavior is identical — the `if (!mounted) return` branches stay exactly as before. The dead-flag smell is pre-existing and out of scope.)

- [ ] **Step 2: Verify the rule is gone**

Run:
```bash
npx eslint .
```
Expected: error total drops by 1 (≈ **42 errors**); `prefer-const` no longer listed.

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/AdminDatabase.tsx
git commit -m "fix(lint): prefer-const in AdminDatabase (#210)"
```

---

## Task 3: Fix `no-empty` + co-located `no-unused-vars` in e2e (7 + 3 sites)

These are empty `catch` blocks in Playwright tests. Three of them (`schedulers.live.spec.ts`) also have an unused `(e)` binding — dropping the binding and adding a comment fixes both rules in one edit.

**Files:**
- Modify: `client/tests/e2e/fixtures/auth.fixture.ts:52-54`
- Modify: `client/tests/e2e/local-only.spec.ts:70`
- Modify: `client/tests/e2e/schedulers.live.spec.ts:19-21`

- [ ] **Step 1: Fix `auth.fixture.ts` (3 empty catches)**

Replace lines 52-54:
```ts
    try { window.localStorage.setItem('token', t); } catch {}
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch {}
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch {}
```
with:
```ts
    try { window.localStorage.setItem('token', t); } catch { /* storage unavailable */ }
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch { /* storage unavailable */ }
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch { /* storage unavailable */ }
```

- [ ] **Step 2: Fix `local-only.spec.ts:70` (1 empty catch)**

Replace:
```ts
    try { window.localStorage.setItem('token', t); } catch {}
```
with:
```ts
    try { window.localStorage.setItem('token', t); } catch { /* storage unavailable */ }
```

- [ ] **Step 3: Fix `schedulers.live.spec.ts:19-21` (empty catch + unused binding)**

Replace lines 19-21:
```ts
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch (e) {}
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch (e) {}
    try { window.localStorage.setItem('token', t); } catch (e) {}
```
with:
```ts
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch { /* storage unavailable */ }
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch { /* storage unavailable */ }
    try { window.localStorage.setItem('token', t); } catch { /* storage unavailable */ }
```

- [ ] **Step 4: Verify**

Run:
```bash
npx eslint .
```
Expected: error total drops by 10 (≈ **32 errors**); `no-empty` no longer listed; the three `schedulers.live.spec.ts` `no-unused-vars` entries gone.

- [ ] **Step 5: Commit**

```bash
git add client/tests/e2e/fixtures/auth.fixture.ts client/tests/e2e/local-only.spec.ts client/tests/e2e/schedulers.live.spec.ts
git commit -m "fix(lint): empty e2e catch blocks (#210)"
```

---

## Task 4: Fix `no-useless-catch` + co-located unused outer-catch (11 + 2 sites)

`try { … } catch (e) { throw e }` is a pure rethrow — unwrap it. In `localApi.ts` the outer `catch (err)` is additionally unused; collapsing the useless inner catch and dropping the unused outer binding fixes both rules.

**Files:**
- Modify: `client/src/hooks/useRemoteServers.ts` (9 rethrow wrappers)
- Modify: `client/src/lib/localApi.ts:282-303` and `:316-337` (2 nested blocks)

- [ ] **Step 1: Unwrap the 9 rethrow wrappers in `useRemoteServers.ts`**

Each of these has the shape `try { <body> } catch (err) { throw err }`. Remove the `try {`, the `} catch (err) { throw err }`, and re-indent the body. The nine `useCallback` bodies are at lines ~24, ~34, ~44, ~53, ~61, ~112, ~122, ~132, ~141. Concrete example — `createProfile` (lines 23-31):

```ts
  const createProfile = useCallback(async (data: api.ServerProfileCreate) => {
    try {
      const newProfile = await api.createServerProfile(data);
      setProfiles([newProfile, ...profiles]);
      return newProfile;
    } catch (err) {
      throw err;
    }
  }, [profiles]);
```
becomes:
```ts
  const createProfile = useCallback(async (data: api.ServerProfileCreate) => {
    const newProfile = await api.createServerProfile(data);
    setProfiles([newProfile, ...profiles]);
    return newProfile;
  }, [profiles]);
```

Apply the identical transformation to the other eight wrappers in the file. Do NOT touch any `try/catch` that does real work in the `catch` (e.g. `loadProfiles` around line 15, which sets an error message and has a `finally` — leave that one alone; it does not trigger `no-useless-catch`).

- [ ] **Step 2: Fix the two nested blocks in `localApi.ts`**

For `shutdown()` (lines 282-303):
```ts
    try {
      return await this.request('/system/shutdown', { method: 'POST' });
    } catch (err) {
      // Fallback for dev setup where backend runs on same origin (uvicorn on :8000)
      // or when the local HTTP proxy is not available. Attempt a same-origin call.
      try {
        const res = await fetch(buildApiUrl(`${API_PREFIX}/system/shutdown`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new LocalApiError(errData.detail || `HTTP ${res.status}`, res.status);
        }
        return await res.json();
      } catch (err2) {
        throw err2;
      }
    }
```
becomes (drop unused outer `err` → `catch {`; unwrap useless inner `try/catch (err2)`):
```ts
    try {
      return await this.request('/system/shutdown', { method: 'POST' });
    } catch {
      // Fallback for dev setup where backend runs on same origin (uvicorn on :8000)
      // or when the local HTTP proxy is not available. Attempt a same-origin call.
      const res = await fetch(buildApiUrl(`${API_PREFIX}/system/shutdown`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new LocalApiError(errData.detail || `HTTP ${res.status}`, res.status);
      }
      return await res.json();
    }
```

Apply the structurally identical transformation to `restart()` (lines 316-337): change the outer `} catch (err) {` to `} catch {`, and unwrap the inner `try { … } catch (err2) { throw err2 }` to just its body. The inner fetch body for `restart()` targets `/system/restart` — keep its existing contents, only remove the redundant `try`/`catch` scaffolding and re-indent.

- [ ] **Step 3: Verify**

Run:
```bash
npx eslint .
```
Expected: error total drops by 13 (≈ **19 errors**); `no-useless-catch` no longer listed; the two `localApi.ts` `no-unused-vars` entries (lines 284, 318) gone.

- [ ] **Step 4: Confirm no behavior regression in this file**

Run:
```bash
npx vitest run
```
Expected: PASS (no test references the unwrapped error scaffolding; this confirms the rethrow removal is behavior-preserving).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useRemoteServers.ts client/src/lib/localApi.ts
git commit -m "fix(lint): remove useless rethrow catches (#210)"
```

---

## Task 5: Fix remaining `no-unused-vars` (19 sites)

After Tasks 1/3/4, the remaining `no-unused-vars` errors fall into three mechanical categories. (The 8 already-`_`-prefixed sites — `vite.config.ts` ×5, `CloudImportPage` `_isDirectory`, `RaidManagement` `_arrayName`, `NotificationPreferencesPage` `_preferences` — were auto-resolved by the ignore pattern in Task 1 and need no edits.)

**Category A — unused test imports (remove the name from the `import`):**
- `client/src/__tests__/api/schedulers.test.ts:1` — remove `vi` and `beforeEach` from the `vitest` import.
- `client/src/__tests__/hooks/useConfirmDialog.test.tsx:2` — remove the unused name (col 35) from its import.
- `client/src/__tests__/lib/adminDbFormatters.test.ts:1` — remove the unused name (col 32).
- `client/src/__tests__/lib/errorHandling.test.ts:1` — remove the unused name (col 32).
- `client/src/__tests__/lib/secureStore.test.ts:1` — remove the unused name (col 32).

**Category B — unused `catch` bindings (change `catch (x) {` → `catch {`):**
- `client/src/components/benchmark/BenchmarkPanel.tsx:116`, `:128`
- `client/src/components/power/SleepConfigPanel.tsx:173`
- `client/src/components/rate-limits/RateLimitsTab.tsx:213`, `:235`
- `client/src/pages/PluginsPage.tsx:63`, `:81`, `:107`, `:126`
- `client/src/pages/SyncPrototype.tsx:75`, `:102`
- `client/src/pages/Login.tsx:95` — change `} catch (localErr: unknown) {` to `} catch {` (the `setConnectionMode('fallback')` body stays).

**Category C — unused type import:**
- `client/src/types/plugin-sdk.d.ts:9` — change `import type { LucideIcon, LucideProps } from 'lucide-react';` to `import type { LucideIcon } from 'lucide-react';` (drop the unused `LucideProps`).

- [ ] **Step 1: Apply Category A (5 files)**

For each test file, open it and delete the unused identifier from the `import { … } from 'vitest'` (or relevant module) line. Example — `schedulers.test.ts:1`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
```
becomes:
```ts
import { describe, it, expect } from 'vitest';
```
For the other four, the ESLint message names the exact unused identifier at the given column — remove only that name, keep the rest of the import.

- [ ] **Step 2: Apply Category B (6 files)**

For each listed `catch` site, drop the binding. The general edit is `} catch (err) {` → `} catch {` (the binding name varies — `err`, `e`, `localErr`; whatever appears at that line). Do not change the catch body. Verify each block still references no removed binding (if a body actually uses the variable, ESLint would not have flagged it — these are all genuinely unused).

- [ ] **Step 3: Apply Category C (1 file)**

Edit `client/src/types/plugin-sdk.d.ts:9` as shown above.

- [ ] **Step 4: Verify zero errors**

Run:
```bash
npx eslint .
```
Expected: exit code **0**. Summary shows **0 errors** and only warnings (`no-explicit-any`, `exhaustive-deps`, `only-export-components`). `no-unused-vars` no longer listed.

- [ ] **Step 5: Commit**

```bash
git add client/src/__tests__ client/src/components/benchmark/BenchmarkPanel.tsx client/src/components/power/SleepConfigPanel.tsx client/src/components/rate-limits/RateLimitsTab.tsx client/src/pages/PluginsPage.tsx client/src/pages/SyncPrototype.tsx client/src/pages/Login.tsx client/src/types/plugin-sdk.d.ts
git commit -m "fix(lint): drop unused vars, catch bindings, and imports (#210)"
```

---

## Task 6: Wire the blocking lint step into CI

**Files:**
- Modify: `.github/workflows/ci-check.yml` (`frontend-build` job)

- [ ] **Step 1: Insert the lint step**

In `.github/workflows/ci-check.yml`, inside the `frontend-build` job, insert a new step **between** the `Install dependencies` step and the `Build` step (fail-fast: lint before the slower build). The result must read:

```yaml
      - name: Install dependencies
        working-directory: client
        run: npm ci

      - name: Lint (ESLint)
        working-directory: client
        run: npx eslint .

      - name: Build
        working-directory: client
        run: npm run build
```

Do not change the runner (`ubuntu-latest`), triggers, or any other job. This step touches no self-hosted runner and none of the four CI/CD-security layers.

- [ ] **Step 2: Validate the workflow YAML locally**

Run (from repo root):
```bash
cd "D:/Programme (x86)/Baluhost" && python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci-check.yml')); print('YAML OK')"
```
Expected: `YAML OK` (no parse error).

- [ ] **Step 3: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add .github/workflows/ci-check.yml
git commit -m "ci: enforce ESLint in frontend-build (blocking) (#210)"
```

---

## Task 7: Final full verification

**Files:** none (verification only)

- [ ] **Step 1: ESLint green**

```bash
cd "D:/Programme (x86)/Baluhost/client" && npx eslint .
```
Expected: exit **0**, **0 errors** (warnings allowed).

- [ ] **Step 2: Build green (no TS regression from the edits)**

```bash
npm run build
```
Expected: build succeeds (`tsc -b && vite build` exit 0).

- [ ] **Step 3: Vitest green (no behavior regression)**

```bash
npx vitest run
```
Expected: all tests pass.

- [ ] **Step 4: Confirm clean tree**

```bash
cd "D:/Programme (x86)/Baluhost" && git status --short
```
Expected: no unexpected modified/untracked files from this work (the unrelated pre-existing untracked plan file under `docs/superpowers/plans/2026-06-13-presence-heartbeat-...` may remain — do not commit it).

When all four pass, the branch is ready for PR against `main`.

---

## Notes for the PR

- PR title suggestion: `ci(lint): enforce ESLint in CI + fix cheap errors (#210)`.
- Mention in the PR body that the 4 `react-hooks/rules-of-hooks` hits were Playwright false-positives (not bugs), resolved by the e2e exclusion.
- Link follow-ups #244 / #245 / #246 as the staged ramp.
- `.github/workflows/` is CODEOWNERS-owned → expect Xveyn review (Layer 1, advisory on `main`).
