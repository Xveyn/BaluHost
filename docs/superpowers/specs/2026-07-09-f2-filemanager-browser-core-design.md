# F2 — FileManager Browser-Core Decomposition + Query Migration (PR-1, Design)

**Date:** 2026-07-09
**Finding:** F2 (#301, part of #298) — 22 non-test components > 500 lines violate the
`pages/CLAUDE.md` "minimal logic in page files" convention. Also closes the
FileManager slice of F1 (#299): `FileManager.tsx` still hand-rolls a
`sessionStorage` file cache instead of using TanStack Query + the app-wide persister.
**Scope of this spec:** the FIRST of **two stacked PRs** for `client/src/pages/FileManager.tsx`
(currently 914 lines). This PR = the **browser core**. PR-2 (VCL slice + upload/drag-drop
hook + final page cleanup) gets its own spec → plan → PR.

## Goal

Move the browsing core — mountpoints, the file list, navigation, and file CRUD —
out of the page into one cohesive **query-backed hook** (`useFileBrowser`) plus
**pure helpers**, and replace the hand-rolled `sessionStorage` file cache
(`files_cache_${fullPath}`) with `useQuery`. The app-wide query persister
(`queryPersister.ts`) then provides F5 instant-paint for free.

This is behavior-preserving **except** the intended cache-mechanism swap
(manual `sessionStorage` → TanStack Query cache/persister).

## Why FileManager is different from PowerManagement

The page's JSX is **already** componentized: all 8 modals (`NewFolderDialog`,
`DeleteDialog`, `RenameDialog`, `FileViewer`, `VersionHistoryModal`,
`PermissionEditor`, `OwnershipTransferModal`, `ShareFileModal`) plus `FileListView`
and `StorageSelector` are extracted into `components/file-manager/`. The 914 lines
are almost entirely **logic**: ~28 `useState`, ~8 `useEffect`, file CRUD,
drag-drop directory traversal, the sessionStorage cache, and a self-contained
VCL/versioning slice. So the decomposition unit here is the **custom hook +
pure helper**, not presentational components.

## Current state (relevant facts, verified against the code)

- `storageInfo` is **derived**, not fetched: `loadStorageInfo` (`:287-296`) just
  copies `selectedMountpoint.{size,used,available}_bytes`. The
  `sessionStorage.removeItem('storage_info_cache')` calls reference a key that is
  never set or read — dead. So the only real reads in the browser core are
  **mountpoints** (`GET /api/files/mountpoints`, once on mount) and the **file
  list** (`GET /api/files/list?path=fullPath`).
- `loadFiles` (`:309-362`) caches each listing under `files_cache_${fullPath}`
  and re-reads it for instant paint. This is the manual cache being replaced.
- `mountpoints` load auto-selects the default mountpoint (`is_default` or `[0]`)
  and resets `currentPath` to `''`.
- Navigation: `getFullPath` (`:298-307`), `navigateToFolder` (`:547-557`),
  `goBack` (`:559-564`).
- Browser-core mutations: `handleCreateFolder` (`:398-418`), `handleDelete`
  (`:425-441`), `handleRename` (`:449-470`) — each posts/deletes/puts then
  `sessionStorage.removeItem(...)` + `loadFiles(currentPath, false)`.
  `handleDownload` (`:378-396`) streams a blob (no cache effect).
- The `queryKeys.files` domain does **not** exist yet.

## In scope (PR-1)

### 1. `lib/queryKeys.ts` — new `files` domain

```ts
files: {
  all: () => ['files'] as const,
  mountpoints: () => ['files', 'mountpoints'] as const,
  /** Directory listing; the resolved full path is part of the key. */
  list: (fullPath: string) => ['files', 'list', fullPath] as const,
}
```

### 2. `components/file-manager/utils.ts` — pure helpers (new file, unit-tested)

- `mapApiFileItem(raw: ApiFileItem): FileItem` — the exact mapping currently
  inline in `loadFiles` (`:332-350`), including the `sync_info` remap and the
  `modified_at ?? mtime ?? now` / `ownerId ?? owner_id` / `can_*` fallbacks.
- `getFullPath(mountpoint: StorageMountpoint | null, relativePath: string): string`
  — pure form of `:298-307` (dev-storage passthrough; otherwise
  `${mountpoint.path}/${clean}` or `mountpoint.path`).
- `toRelativePath(mountpoint: StorageMountpoint | null, folderPath: string): string`
  — the `navigateToFolder` transform (`:547-557`): strip the mountpoint prefix
  for non-dev-storage, else return `folderPath` unchanged.
- `parentPath(currentPath: string): string` — the `goBack` transform (`:559-564`).

> `mapApiFileItem` references `ApiFileItem`/`FileItem` from
> `components/file-manager/types.ts`. To avoid depending on `new Date()` (banned
> in some contexts but fine in the browser), it keeps the existing
> `?? new Date().toISOString()` fallback — this runs in the browser, not a
> workflow script, so it is allowed.

### 3. `hooks/useFileBrowser.ts` — the browser-core hook (new file)

Owns and returns:
- `mountpoints` via `useQuery(queryKeys.files.mountpoints(), …)`;
  `selectedMountpoint` state auto-set to the default once mountpoints load;
  `selectMountpoint(mp)` sets it and resets `currentPath` to `''`.
- `currentPath` state; `navigateToFolder(folderPath)` (via `toRelativePath`);
  `goBack()` (via `parentPath`).
- `fullPath` = `getFullPath(selectedMountpoint, currentPath)` (memoized).
- `files` via `useQuery(queryKeys.files.list(fullPath), …, { enabled: !!selectedMountpoint })`,
  mapping the response with `mapApiFileItem`. Replaces the sessionStorage cache.
- `storageInfo` derived from `selectedMountpoint` (or `null`).
- `loading` = the list query's `isFetching`. The original set `loading` true on
  **every** `loadFiles` call (start → `finally`), so `isFetching` is the exact
  match (`isLoading` is true only on the first uncached load). The page's spinner
  (`loading && files.length === 0`) and `FileListView`'s `loading` prop both keep
  working; with a fresh (unpersisted) folder key `files` is `[]` and `isFetching`
  is true → spinner shows, matching the old no-cache path; with a persisted key
  `files` paints instantly while a background refetch runs.
- Mutations (`useMutation`, each `onSuccess` invalidates `files.list(fullPath)`):
  `createFolder(name)`, `deleteFile(file)`, `renameFile({ file, newName })`.
  They preserve the existing toast keys and error extraction (`getErrorMessage` +
  the `err.response.data` unwrap).
- `downloadFile(file)` — passthrough (blob stream), unchanged.
- `refresh()` — `invalidateQueries(files.list(fullPath))`, for the page's
  `onUploadsComplete` and the version-restore callback.

Public shape is designed so the page and `FileListView` consume it without prop
churn (`files`, `loading`, `storageInfo`, `mountpoints`, `selectedMountpoint`,
`currentPath`, and the handlers above).

### 4. `pages/FileManager.tsx` — wire the hook

- Replace the browser-core state (`files`, `currentPath`, `loading`,
  `mountpoints`, `selectedMountpoint`, `storageInfo`) and the functions
  `loadFiles`/`loadMountpoints`/`loadStorageInfo`/`getFullPath`/
  `navigateToFolder`/`goBack`/`handleCreateFolder`/`handleDelete`/
  `handleRename`/`handleDownload` with `useFileBrowser()`.
- Delete the mount-load `useEffect` and the `[currentPath, selectedMountpoint]`
  load-effect (query-driven now) and all `files_cache_*` / `storage_info_cache`
  `sessionStorage` lines.
- Modal open/close + input state (new-folder name, `fileToDelete`,
  `fileToRename` + `newFileName`) **stays in the page** and calls the hook's
  mutations. `StorageSelector`'s `onSelect` calls `selectMountpoint`.
- `onUploadsComplete` calls `refresh()` for the list; its VCL reloads
  (`loadVclQuota`, `loadUserRootUsage`) stay untouched (PR-2).

## Out of scope (PR-2, untouched here)

VCL (quota, user-root-usage, per-file version-counts, tracking rules + toggle),
upload + drag-drop handlers (`handleUpload`/`handleFolderUpload`/`handleDrag`/
`traverseFileTree`/`handleDrop`/`dragActive`), the permission/ownership/share
modals and their handlers, and the `files`-driven effects (version-counts,
tracking, owner-name cache) — these keep reading the hook's `files` in the
interim. No UX/layout change. No new dependencies.

After PR-1 the page is ~700 lines (down from 914); PR-2 finishes it to ~450.

## Testing

The house pattern for query-backed hooks is `renderHook` + a real
`createQueryWrapper` (used across the F1 migrations this session), plus plain
unit tests for pure helpers. That is the "full" testing equivalent for a
hook-shaped change; whole-page RTL is not attempted (the missing `renderWithProviders`/MSW
infra — assessment T2 — makes it costly and low-value).

1. **`__tests__/components/file-manager/utils.test.ts`** (pure):
   - `mapApiFileItem`: maps a full API item (incl. `sync_info`, `owner_id`
     fallback, `can_*`), and the minimal item (fallback timestamp path).
   - `getFullPath`: dev-storage passthrough; non-dev prefix join; empty path →
     `mountpoint.path`; leading-slash cleanup; `null` mountpoint → relativePath.
   - `toRelativePath`: strips the mountpoint prefix (non-dev), returns unchanged
     for dev-storage / non-matching prefix.
   - `parentPath`: nested → parent; single segment → `''`; `''` → `''`.
2. **`__tests__/hooks/useFileBrowser.test.tsx`** (`renderHook` + `createQueryWrapper`,
   api modules mocked):
   - mountpoints load → `selectedMountpoint` is the default; `currentPath === ''`.
   - the list query is keyed on the resolved `fullPath`; `files` are mapped;
     `navigateToFolder` changes `currentPath` → a new listing is requested.
   - `createFolder`/`deleteFile`/`renameFile` call the right endpoint and
     invalidate `files.list(fullPath)` (assert a refetch / `invalidateQueries`).
   - `enabled` gating: no list request before a mountpoint is selected.

## Verification

- New tests green.
- Full frontend `vitest run` green (no regressions).
- `eslint .` 0 errors; `npm run build` (tsc -b + vite) green.

## Notes / risks

- FileManager has **no existing tests** and is the NAS core. The hook tests +
  helper tests are the safety net for the cache-mechanism swap. The behavior
  contract to preserve: same listings, same navigation, same CRUD toasts, and
  a refetch after each mutation / upload-complete / version-restore.
- `staleTime` stays at the app default (0) — the list refetches on mount/param
  change, matching the current always-fetch behavior; the persister supplies the
  instant-paint the old `sessionStorage` cache used to. No polling is introduced
  (FileManager never polled).
