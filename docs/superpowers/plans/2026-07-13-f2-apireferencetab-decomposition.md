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

## Verification

- Per-unit Vitest: pure helper (branch coverage), `EndpointCard`, `useApiReference`,
  plus render-smoke tests for `ApiCategoryTabs` / `ApiSectionList` (click → setter).
- Gates before PR: `eslint .` (0 errors), `npm run build` (tsc -b), `npx vitest run`.
- Browser smoke (Manual → API reference): category/sub-tab switch, search filters,
  card open/close + copy, refresh, admin Docs↔Rate-Limits toggle. No full Playwright
  (no interaction subtlety like FanCurveChart).
- Whole-branch review (Opus) — byte-for-behaviour fidelity check.

## Non-goals (YAGNI)

- No behaviour change, no re-design, no new deps.
- Do not refactor the `getApiBaseUrl` heuristic or the rate-limit branch logic — port verbatim.
