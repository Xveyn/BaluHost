# F2 — FileManager VCL + Upload Extraction (PR-2, Design)

**Date:** 2026-07-09
**Finding:** F2 (#301, part of #298) — `pages/CLAUDE.md` "minimal logic in page files".
**Scope of this spec:** the SECOND of two stacked PRs for `client/src/pages/FileManager.tsx`.
PR-1 (browser core → `useFileBrowser`, merged) brought the page 914 → 700. PR-2
extracts the two remaining logic clusters — the **VCL slice** and **upload/drag-drop**
— so the page finishes as a composition root under the 500-line convention.

## Goal

Bring `FileManager.tsx` from **700 → ~470 lines** by extracting:
1. the VCL/versioning slice into `hooks/useVclFileInfo.ts`,
2. the upload/drag-drop logic into `hooks/useFileUpload.ts`,
3. the owner-name-cache derivation into a pure helper + `useMemo`.

Behavior-preserving **except** the two simple VCL reads (quota, user-root-usage)
move to TanStack Query — the same cache-swap direction as PR-1.

## Current state (post-PR-1, 700 lines)

The page already consumes `useFileBrowser` (browser core). What remains oversized:
- **VCL state + logic** (~130 lines): `vclQuota`, `userRootUsageBytes`,
  `versionCounts`, `trackingStatus`, `vclMode`, `showVersionHistory`,
  `versionHistoryFile`; `loadVclQuota` (`:132-163`), `loadUserRootUsage`
  (`:165-172`), the version-counts effect (`:175-202`), the tracking-info effect
  (`:205-239`), `handleToggleTracking` (`:389-428`), `handleVersionHistory`
  (`:384-387`).
- **Upload/drag-drop** (~95 lines): `dragActive`; `handleUpload` (`:254-259`),
  `handleFolderUpload` (`:261-266`), `handleDrag` (`:279-287`), `traverseFileTree`
  (`:289-323`), `handleDrop` (`:325-348`).
- **Owner-name cache** (~10 lines): `userCache` state + effect (`:242-250`).
- Permission/ownership/share modal orchestration (`allUsers`, `handleEditPermissions*`,
  transfer, share) + the thin new-folder/delete/rename/viewer modal state — these
  **stay in the page** as the composition root.

## Components to extract

### A. `hooks/useVclFileInfo.ts`

Signature: `useVclFileInfo(files: FileItem[]): UseVclFileInfoResult`.

Owns and returns `{ vclQuota, userRootUsageBytes, versionCounts, trackingStatus,
vclMode, toggleTracking, refreshVcl }`.

- **`vclQuota`** — `useQuery(queryKeys.vcl.quota())` over `vclApi.getUserQuota()`,
  mapped to `{ usagePercent, warning, current, max } | null`. The `warning` level
  comes from the pure helper `vclWarningLevel(pct)`. The **warning/critical toast**
  (currently fired inside `loadVclQuota`) moves to an effect keyed on the quota
  data, so it still fires on the initial load and on the post-upload refetch.
  Query errors are swallowed (matches the original silent `catch`).
- **`userRootUsageBytes`** — `useQuery(queryKeys.files.userRootUsage())` over
  `getUserRootUsage()`; `data?.user_root_used_bytes ?? null`. Silent on error.
- **`versionCounts`** and **`trackingStatus`/`vclMode`** — **remain effect-driven
  inside the hook**, moved verbatim from the page's two `[files]` effects
  (Promise.all fan-outs with per-file partial-failure tolerance). See the
  deliberate design decision below.
- **`toggleTracking(file)`** — the existing `handleToggleTracking` logic, moved
  verbatim (optimistic `setTrackingStatus` + `add/removeTrackingRule` per
  automatic/manual mode, its toasts and error toast preserved).
- **`refreshVcl()`** — `invalidateQueries` for the quota + user-root-usage keys,
  called by the page's `onUploadsComplete` effect. (The version-counts/tracking
  effects re-run automatically when `files` changes after an upload, so they need
  no explicit refresh.)

Pure helper `vclWarningLevel(usagePercent: number): 'warning' | 'critical' | null`
(`>= 95` critical, `>= 80` warning, else null) — co-located, unit-tested.

`versionHistoryFile`/`showVersionHistory` modal state and `handleVersionHistory`
stay in the page (thin modal open/close, like the other modals).

### B. `hooks/useFileUpload.ts`

Signature: `useFileUpload(opts: { getFullPath: () => string; availableBytes?: number }): UseFileUploadResult`.

Calls `useUpload()` internally for `startUpload` + `isUploading`. Owns `dragActive`
and returns `{ dragActive, isUploading, handleUpload, handleFolderUpload,
handleDrag, handleDrop }`. `traverseFileTree` is an internal (module-private)
function. The three `startUpload(fileList, getFullPath(), availableBytes)` call
sites are preserved verbatim.

The hidden `<input>` refs (`fileInputRef`/`folderInputRef`) stay in the page (they
are render concerns and are only used as `ref=`).

### C. Owner-name cache → pure helper

`buildOwnerNameCache(files: FileItem[]): Record<string, string>` (from the
`:242-250` effect body) + `const userCache = useMemo(() => buildOwnerNameCache(files), [files])`
in the page. Removes the `userCache` state and effect. Unit-tested.

## Deliberate design decision — VCL fan-outs stay effect-based

The two per-file fan-outs (`versionCounts` via `vclApi.getFileVersions`,
`trackingStatus` via `getTrackingRules` + `checkFileTracking`) are **intentionally
kept as `useEffect` + `Promise.all` inside `useVclFileInfo`, not migrated to
`useQuery`**, even though PR-1 and the simple VCL reads use Query. Rationale:

- They are **N+1 fan-outs with per-file partial-failure tolerance** (each file's
  fetch is independently try/caught and skipped on error) — expressing that in a
  single `useQuery` queryFn is awkward and loses the "one bad file doesn't fail the
  batch" property.
- They are **page-scoped** (only FileManager mounts them) and driven entirely by
  the current `files` list, so there is **no cross-mount dedup/persister benefit**
  — the main upside of Query migration doesn't apply.
- Query-keying on the **file-id list** (an array key that changes on every
  navigation) adds complexity and cache churn for no observable gain.

They therefore move **verbatim** into the hook (same effects, same tolerance),
re-running on `files` change exactly as today. This keeps PR-2's risk low on the
still-lightly-tested page while the simple reads (quota, user-root-usage) get the
Query treatment where it pays off.

## Result

`FileManager.tsx` ~700 → **~470 lines**: the composition root wiring
`useFileBrowser` + `useVclFileInfo` + `useFileUpload`, plus the
permission/ownership/share modal orchestration and the thin modal state. Clears
the F2 <500 convention; completes FileManager for #301.

## Testing

- **`useVclFileInfo`** (`renderHook` + `createQueryWrapper`, api mocked): quota
  query → mapped `vclQuota` incl. `warning` from `vclWarningLevel`; user-root-usage
  → `userRootUsageBytes`; `versionCounts` populated from `files` (fan-out);
  `toggleTracking` flips `trackingStatus` and calls the right add/remove-rule API.
- **`useFileUpload`** (`renderHook`): `dragActive` transitions on drag enter/leave;
  `handleUpload` calls `startUpload(fileList, getFullPath(), availableBytes)` and
  clears the input. `traverseFileTree`/`handleDrop` (elaborate `FileSystemEntry`
  mocking) are low-value/high-effort — lightly covered or skipped.
- **Pure helpers**: `vclWarningLevel` (boundaries 79/80/94/95/100) and
  `buildOwnerNameCache` (skips null/`'null'`/missing owner names).

## Verification

- New tests green.
- Full frontend `vitest run` green (no regressions).
- `eslint .` 0 errors; `npm run build` green.
- `FileManager.tsx` under 500 lines.

## Out of scope

- The permission/ownership/share modals and their handlers (page orchestration).
- `useFileBrowser` and all presentational components — untouched.
- No UX/layout change; no new dependencies.
