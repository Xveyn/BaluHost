# F2 Decomposition — `pages/AdminDatabase.tsx` (#301)

**Date:** 2026-07-13
**Branch:** `refactor/f2-decompose-admindatabase`
**Goal:** Behaviour-preserving decomposition of `AdminDatabase.tsx` (575 → target ~100 lines)
into a thin orchestrator over pure helpers + a state hook + presentation subcomponents.
Same pattern as the prior 13 F2 decompositions (#396–#413).

## Baseline

`AdminDatabase.tsx` (575 lines). Analytics content already delegates to existing
`components/admin/*` (DatabaseStatsCards, StorageAnalysisChart, MonitoringHistoryViewer,
MaintenanceTools, RetentionSettings). The bulk is the **browse** view + wiring:

- Browse state + 2 react-query hooks + derived values (lines 26–98)
- Handlers: select/sort/filter/rowClick (110–135)
- `loadOwners` owner-map loader with page-size fallback loop (138–177)
- `handleCsvExport` DOM download (179–192)
- `renderBrowseContent` ~260 lines JSX (195–456)
- `renderAnalyticsContent` switch (459–494)
- Header + two-level category/subtab nav + return (496–574)

Existing coverage to keep green: `__tests__/hooks/useAdminDb.test.tsx`,
`__tests__/lib/adminDbFormatters.test.ts`.

## Target Units

1. **`lib/adminOwnerMap.ts`** (pure) — `buildOwnerMap(rows)`: id/name coalescing (was lines 152–156).
   Tested: id key variants (id/ID/user_id/userId), name variants, missing id skipped.
2. **`hooks/useAdminDatabaseBrowse.ts`** — all browse state, both queries, derived values
   (schema/rows/total/loading/error/totalPages/rangeStart/rangeEnd/activeFilterCount),
   handlers (table select, sort, filters, row click), `loadOwners`, `handleCsvExport`,
   debounced search. Tested via `renderHook`: reset-on-select, page-clamp derivations,
   loadOwners success/fallback/guard, csv guard.
3. **`components/admin/admin-database/`** presentation:
   - `BrowseToolbar.tsx` — search, filter toggle, page-size, pagination, CSV, row-count
   - `SchemaStrip.tsx` — column type strip
   - `OwnerMappingDetails.tsx` — `<details>` owner-mapping block
   - `AnalyticsTabs.tsx` — subtab bar + content switch
   - `DatabaseCategoryNav.tsx` — header + Browse/Analytics category pills
   - `TableBrowser.tsx` — composes sidebar + panel + toolbar + schema strip + owner mapping
     + data table + row detail (the whole browse view)
4. **`AdminDatabase.tsx`** — thin: header via nav, category pill state, delegates to
   `<TableBrowser>` / `<AnalyticsTabs>`.

## Verification

- Per-unit Vitest for pure helper + hook + each presentation component.
- Gates before PR: `eslint .` (0 errors), `npm run build` (tsc -b), `npx vitest run`.
- Whole-branch review (Opus) — byte-for-behaviour fidelity check.
