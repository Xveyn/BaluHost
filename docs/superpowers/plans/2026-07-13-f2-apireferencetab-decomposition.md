# F2 Decomposition — `components/manual/ApiReferenceTab.tsx` (#301)

**Date:** 2026-07-13
**Branch:** `refactor/f2-decompose-apireferencetab`
**Goal:** Behaviour-preserving decomposition of `ApiReferenceTab.tsx` (565 → target ~90–130 lines)
into a thin orchestrator over a pure helper + a state hook + presentation subcomponents.
Same pattern as the prior 14 F2 decompositions (#396–#414). Full split (Variante A).

## Baseline

`ApiReferenceTab.tsx` (565 lines). A docs/reference tab — mostly presentational, one
admin-only fetch, no drag/touch interaction subtleties. Current pieces:

- `RateLimitConfig` type (25–34)
- `matchEndpointToRateLimitType(method, path)` — pure, ~74 lines, ~40 ordered branches
  mirroring backend rate-limit decorator assignment (36–115)
- `EndpointCard` — presentational card with local `isOpen`/`copied` state (117–235)
- `ApiReferenceTab` orchestrator: state (`activeView`, `selectedCategory`, `selectedSection`,
  `searchQuery`, `rateLimits`, `loading`), `loadRateLimits` fetch, `visibleSections` memo,
  `getApiBaseUrl`, `currentCategorySections`, and the full JSX (view toggle, refresh,
  schema error, base-url card, search, category/sub-tabs, loading skeleton, section list)
  (237–564)

The component has **0 existing tests** → this decomposition is a net test gain.

## Target Units

1. **`lib/apiRateLimitMatch.ts`** (pure — the test centrepiece)
   - `matchEndpointToRateLimitType(method, path): string | null` — **byte-identical port**.
     Branch order is behaviour-relevant (specific-before-generic) → copied 1:1.
   - `RateLimitConfig` interface (shared by hook + `EndpointCard`).
   - Tested: auth specificity-before-generic, files specific→generic, shares
     POST/PATCH/DELETE vs GET, system GET vs non-GET, VCL/SSD-cache GET split,
     admin catch-all prefixes, `null` fallback for unmatched paths.

2. **`hooks/useApiReference.ts`** — `useApiReference({ isAdmin, token })`
   - State: `activeView`, `selectedCategory`, `selectedSection`, `searchQuery`,
     `rateLimits`, `loading` (+ setters).
   - `loadRateLimits` fetch of `/api/admin/rate-limits` (admin-gated; empty catch preserved).
   - `useEffect([isAdmin])` load/skip logic 1:1; `visibleSections` memo, `currentCategorySections`,
     `apiBaseUrl` (from `getApiBaseUrl`), and pass-through of `useOpenApiSchema()`
     (`apiSections`/`apiCategories`/`schemaLoading`/`schemaError`/`refetchSchema`).
   - Tested via `renderHook`: admin loads + maps by `endpoint_type`; non-admin skips fetch
     and sets `loading=false`; `visibleSections` filters correctly for search / category / section.

3. **`components/manual/api-reference/`** presentation (pure props, no fetch):
   - `EndpointCard.tsx` — keeps local `isOpen`/`copied`; uses `matchEndpointToRateLimitType`.
   - `ApiViewToggle.tsx` — Docs | Rate Limits (admin only).
   - `ApiBaseUrlCard.tsx` — base-url infobox + copy.
   - `ApiSearchBar.tsx` — search input + clear.
   - `ApiCategoryTabs.tsx` — category pills + per-category sub-tabs.
   - `ApiSchemaError.tsx` — error banner + retry.
   - `ApiLoadingSkeleton.tsx` — pulse skeleton.
   - `ApiSectionList.tsx` — section header + `EndpointCard` list.
   - `index.ts` — barrel re-export.

4. **`ApiReferenceTab.tsx`** — thin: calls `useApiReference`, wires subcomponents, keeps
   top-level layout (`space-y-*`, Docs/Limits switch, `RateLimitsTab` when `activeView==='limits'`).

All Tailwind classes, `t()` keys, and icons carried over verbatim. `getApiBaseUrl`
port heuristic (3001 dev / 8000 prod) ported unchanged — not "cleaned up".

## Test Plan

Component has **0 existing tests** → net gain (~35 new tests, comparable to
RaidSetupWizard +31 / FanDetails +26). Style mirrors `__tests__/lib/adminOwnerMap.test.ts`.

**1. `lib/apiRateLimitMatch.ts` — the centrepiece (~22 tests).** The matcher has ~40
*ordered* branches (specific-before-generic); the ordering is behaviour-relevant, so each
critical priority is pinned:

| Pinned case | expected | why order-sensitive |
|---|---|---|
| `POST /api/auth/login` | `auth_login` | before `/api/auth/*` catch (`user_operations`) |
| `POST /api/auth/2fa/setup` | `auth_2fa_setup` | before generic auth catch |
| `POST /api/files/upload/chunked` | `file_chunked` | before `/api/files/upload` → `file_upload` |
| `GET /api/files/download/x` | `file_download` | before `/api/files/` catch (`file_write`) |
| `DELETE /api/files/x` | `file_delete` | method decides |
| `PATCH /api/shares/1` | `share_create` | POST/PATCH/DELETE before GET → `share_list` |
| `POST /api/benchmark/run` | `admin_benchmark` | before admin catch-all (`/api/benchmark/`) |
| `GET` vs `POST /api/system/x` | `system_monitor` / `admin_operations` | GET split |
| `GET` vs `POST /api/vcl/x` | `file_list` / `file_write` | GET split |
| `GET` vs `POST /api/ssd-cache/x` | `file_list` / `admin_operations` | GET split |
| `/api/pihole/…`, `/api/fans/…` (admin prefixes) | `admin_operations` | catch-all |
| `/api/unknown/x` | `null` | fallback |

**2. `EndpointCard` (~4):** renders method/path/auth-shield/rate-limit badge; click
toggles open; copy sets `copied`.

**3. `useApiReference` (renderHook, ~5):** admin loads rate limits + maps by
`endpoint_type`; non-admin skips fetch → `loading=false`; `visibleSections` filters
correctly for search / category / section.

**4. Smoke (`ApiCategoryTabs`, `ApiSectionList`, ~4):** click calls the right setter /
renders the endpoint list.

Purely presentational blocks (`ApiBaseUrlCard`, `ApiSearchBar`, `ApiLoadingSkeleton`,
`ApiSchemaError`) get tests only if they carry logic — no artificial markup tests (YAGNI,
matching prior F2 PRs).

## Verification

- Per-unit Vitest as above.
- Gates before PR: `eslint .` (0 errors), `npm run build` (tsc -b), `npx vitest run`.
- Browser smoke (Manual → API reference): category/sub-tab switch, search filters,
  card open/close + copy, refresh, admin Docs↔Rate-Limits toggle. No full Playwright
  (no interaction subtlety like FanCurveChart).
- Whole-branch review (Opus) — byte-for-behaviour fidelity check.

## Non-goals (YAGNI)

- No behaviour change, no re-design, no new deps.
- Do not refactor the `getApiBaseUrl` heuristic or the rate-limit branch logic — port verbatim.
