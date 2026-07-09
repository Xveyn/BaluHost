# F2 — FileManager Browser-Core (PR-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the FileManager browsing core (mountpoints, file list, navigation, file CRUD) into one query-backed hook `useFileBrowser` + pure helpers, replacing the hand-rolled `sessionStorage` file cache with TanStack Query.

**Architecture:** New pure helpers in `components/file-manager/utils.ts`; new typed api functions in `api/files.ts`; new `hooks/useFileBrowser.ts` owning two `useQuery`s (mountpoints, list) + three mutations (create/delete/rename); page composes the hook. VCL, upload/drag-drop, and the permission/ownership/share modals stay untouched for PR-2.

**Tech Stack:** React 18 + TypeScript, TanStack Query v5, react-i18next, react-hot-toast, Vitest + React Testing Library (`renderHook` + `createQueryWrapper`).

## Global Constraints

- **Behavior-preserving except the intended cache swap.** Same listings, same navigation, same CRUD toasts (exact i18n keys), a refetch after each mutation / upload-complete / version-restore. The only deliberate change: the manual `sessionStorage` file cache (`files_cache_*`) is gone — the list is a `useQuery`, instant-paint now comes from the app-wide persister.
- **No UX/layout change. No new dependencies.**
- `loading` = the list query's `isFetching` (the original set `loading` true on every `loadFiles` call).
- `storageInfo` is **derived** from `selectedMountpoint` (no fetch). `storage_info_cache` sessionStorage is dead — remove it.
- Hooks call **typed `api/*` functions**, never `apiClient` directly (`api/CLAUDE.md`). Add the browser-core functions to `api/files.ts`.
- Test pattern: `renderHook` + `createQueryWrapper` from `src/__tests__/helpers/queryClient` (mock `api/files`, `react-hot-toast`, `react-i18next`); pure helpers get plain unit tests.
- Windows shell: chain with `;`, never `&&`.
- Scope is PR-1 only. Do NOT touch VCL (quota/user-root-usage/version-counts/tracking), upload/drag-drop, or the permission/ownership/share modals — they stay and keep reading the hook's `files`.

---

### Task 1: Pure helpers in `components/file-manager/utils.ts`

**Files:**
- Create: `client/src/components/file-manager/utils.ts`
- Test: `client/src/__tests__/components/file-manager/utils.test.ts`

**Interfaces:**
- Produces:
  - `mapApiFileItem(raw: ApiFileItem): FileItem`
  - `getFullPath(mountpoint: StorageMountpoint | null, relativePath: string): string`
  - `toRelativePath(mountpoint: StorageMountpoint | null, folderPath: string): string`
  - `parentPath(currentPath: string): string`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/file-manager/utils.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { mapApiFileItem, getFullPath, toRelativePath, parentPath } from '../../../components/file-manager/utils';
import type { ApiFileItem, StorageMountpoint } from '../../../components/file-manager/types';

const raid: StorageMountpoint = {
  id: 'a', name: 'Main', type: 'raid', path: '/mnt/main',
  size_bytes: 100, used_bytes: 40, available_bytes: 60, status: 'ok', is_default: true,
};
const dev: StorageMountpoint = { ...raid, id: 'd', type: 'dev-storage', path: 'dev-storage' };

describe('mapApiFileItem', () => {
  it('maps a full API item incl. sync_info and snake_case fallbacks', () => {
    const raw: ApiFileItem = {
      name: 'a.txt', path: 'docs/a.txt', size: 12, type: 'file',
      modified_at: '2026-01-01T00:00:00Z', owner_id: 7, owner_name: 'bob', file_id: 3,
      sync_info: [{ device_name: 'pc', platform: 'windows', sync_direction: 'push', last_reported_at: 't' }],
      can_read: true, can_write: false, can_delete: true,
    };
    expect(mapApiFileItem(raw)).toEqual({
      name: 'a.txt', path: 'docs/a.txt', size: 12, type: 'file',
      modifiedAt: '2026-01-01T00:00:00Z', ownerId: 7, ownerName: 'bob', file_id: 3,
      syncInfo: [{ deviceName: 'pc', platform: 'windows', syncDirection: 'push', lastReportedAt: 't' }],
      canRead: true, canWrite: false, canDelete: true,
    });
  });

  it('falls back mtime->modifiedAt and leaves a timestamp when none given', () => {
    const m = mapApiFileItem({ name: 'x', path: 'x', size: 0, type: 'directory', mtime: 'm1' });
    expect(m.modifiedAt).toBe('m1');
    const n = mapApiFileItem({ name: 'y', path: 'y', size: 0, type: 'file' });
    expect(typeof n.modifiedAt).toBe('string');
    expect(n.syncInfo).toBeUndefined();
  });
});

describe('getFullPath', () => {
  it('passes the relative path through for dev-storage', () => {
    expect(getFullPath(dev, 'docs')).toBe('docs');
  });
  it('joins under the mountpoint path for real mounts', () => {
    expect(getFullPath(raid, 'docs')).toBe('/mnt/main/docs');
    expect(getFullPath(raid, '/docs')).toBe('/mnt/main/docs');
  });
  it('returns the mountpoint path for an empty relative path', () => {
    expect(getFullPath(raid, '')).toBe('/mnt/main');
  });
  it('returns the relative path unchanged with no mountpoint', () => {
    expect(getFullPath(null, 'docs')).toBe('docs');
  });
});

describe('toRelativePath', () => {
  it('strips the mountpoint prefix for real mounts', () => {
    expect(toRelativePath(raid, '/mnt/main/docs')).toBe('docs');
  });
  it('returns unchanged for dev-storage or a non-matching prefix', () => {
    expect(toRelativePath(dev, 'docs')).toBe('docs');
    expect(toRelativePath(raid, '/other/docs')).toBe('/other/docs');
  });
});

describe('parentPath', () => {
  it('drops the last segment', () => {
    expect(parentPath('a/b/c')).toBe('a/b');
  });
  it('returns empty for a single segment or empty input', () => {
    expect(parentPath('a')).toBe('');
    expect(parentPath('')).toBe('');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/file-manager/utils.test.ts`
Expected: FAIL — cannot resolve `../../../components/file-manager/utils`.

- [ ] **Step 3: Create the helpers**

Create `client/src/components/file-manager/utils.ts`:

```ts
import type { ApiFileItem, FileItem, StorageMountpoint } from './types';

/** Maps a raw API file item to the UI `FileItem` shape (moved from FileManager.loadFiles). */
export function mapApiFileItem(file: ApiFileItem): FileItem {
  return {
    name: file.name,
    path: file.path,
    size: file.size,
    type: file.type,
    modifiedAt: file.modified_at ?? file.mtime ?? new Date().toISOString(),
    ownerId: file.ownerId ?? file.owner_id,
    ownerName: file.ownerName ?? file.owner_name,
    file_id: file.file_id,
    syncInfo: file.sync_info?.map((si) => ({
      deviceName: si.device_name,
      platform: si.platform as 'windows' | 'mac' | 'linux',
      syncDirection: si.sync_direction as 'bidirectional' | 'push' | 'pull',
      lastReportedAt: si.last_reported_at,
    })),
    canRead: file.can_read ?? undefined,
    canWrite: file.can_write ?? undefined,
    canDelete: file.can_delete ?? undefined,
  };
}

/** Resolves a relative browser path to the backend full path for a mountpoint. */
export function getFullPath(mountpoint: StorageMountpoint | null, relativePath: string): string {
  if (!mountpoint) return relativePath;
  if (mountpoint.type === 'dev-storage') return relativePath;
  const clean = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
  return clean ? `${mountpoint.path}/${clean}` : mountpoint.path;
}

/** Inverse of getFullPath for navigation: strips the mountpoint prefix (real mounts only). */
export function toRelativePath(mountpoint: StorageMountpoint | null, folderPath: string): string {
  if (mountpoint && mountpoint.type !== 'dev-storage') {
    const prefix = mountpoint.path;
    if (folderPath.startsWith(prefix)) {
      return folderPath.slice(prefix.length).replace(/^\//, '');
    }
  }
  return folderPath;
}

/** Parent of a relative path (drops the last segment). */
export function parentPath(currentPath: string): string {
  const parts = currentPath.split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/file-manager/utils.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/file-manager/utils.ts client/src/__tests__/components/file-manager/utils.test.ts
git commit -m "refactor(files): extract pure file-manager path/mapping helpers (#301)"
```

---

### Task 2: `queryKeys.files` domain + browser-core api functions

**Files:**
- Modify: `client/src/lib/queryKeys.ts`
- Modify: `client/src/api/files.ts`

**Interfaces:**
- Produces:
  - `queryKeys.files.all()`, `queryKeys.files.mountpoints()`, `queryKeys.files.list(fullPath)`
  - `getMountpoints(): Promise<{ mountpoints: StorageMountpoint[] }>`
  - `listFiles(fullPath: string): Promise<{ files: ApiFileItem[] }>`
  - `createFolder(params: { path: string; name: string }): Promise<unknown>`
  - `deleteFile(path: string): Promise<unknown>`
  - `renameFile(params: { old_path: string; new_name: string }): Promise<unknown>`
  - `downloadFileBlob(path: string): Promise<Blob>`

> No dedicated api-wrapper tests: these are thin `apiClient` transcriptions (assessment T4 flags such tests as tautological). They are exercised through the mocked `api/files` in Task 3's hook test.

- [ ] **Step 1: Add the `files` domain to `queryKeys.ts`**

In `client/src/lib/queryKeys.ts`, add a `files` block (e.g. right after the `backups` block):

```ts
  files: {
    all: () => ['files'] as const,
    mountpoints: () => ['files', 'mountpoints'] as const,
    /** Directory listing; the resolved backend full path is part of the key. */
    list: (fullPath: string) => ['files', 'list', fullPath] as const,
  },
```

- [ ] **Step 2: Add the browser-core functions to `api/files.ts`**

At the top of `client/src/api/files.ts`, extend the imports with the shared types (type-only cross-import — these types are the canonical file-manager shapes):

```ts
import type { ApiFileItem, StorageMountpoint } from '../components/file-manager/types';
```

Append these functions to `client/src/api/files.ts`:

```ts
// --- Browser-core (list, mountpoints, folder CRUD, download) ---

export async function getMountpoints(): Promise<{ mountpoints: StorageMountpoint[] }> {
  const res = await apiClient.get('/api/files/mountpoints');
  return res.data;
}

export async function listFiles(fullPath: string): Promise<{ files: ApiFileItem[] }> {
  const res = await apiClient.get('/api/files/list', { params: { path: fullPath } });
  return res.data;
}

export async function createFolder(params: { path: string; name: string }): Promise<unknown> {
  const res = await apiClient.post('/api/files/folder', params);
  return res.data;
}

export async function deleteFile(path: string): Promise<unknown> {
  const res = await apiClient.delete(`/api/files/${encodeURIComponent(path)}`);
  return res.data;
}

export async function renameFile(params: { old_path: string; new_name: string }): Promise<unknown> {
  const res = await apiClient.put('/api/files/rename', params);
  return res.data;
}

export async function downloadFileBlob(path: string): Promise<Blob> {
  const res = await apiClient.get(`/api/files/download/${encodeURIComponent(path)}`, { responseType: 'blob' });
  return res.data;
}
```

- [ ] **Step 3: Typecheck**

Run: `cd client ; npx tsc -b`
Expected: no errors (verifies the new exports + the type import compile).

- [ ] **Step 4: Commit**

```bash
git add client/src/lib/queryKeys.ts client/src/api/files.ts
git commit -m "feat(files): add files query-key domain + browser-core api functions (#301)"
```

---

### Task 3: `useFileBrowser` hook

**Files:**
- Create: `client/src/hooks/useFileBrowser.ts`
- Test: `client/src/__tests__/hooks/useFileBrowser.test.tsx`

**Interfaces:**
- Consumes: the Task 1 helpers, the Task 2 api functions + query keys.
- Produces: `useFileBrowser(): UseFileBrowserResult` with the surface in the code below.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useFileBrowser.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }) }));
vi.mock('../../api/files', () => ({
  getMountpoints: vi.fn(),
  listFiles: vi.fn(),
  createFolder: vi.fn(),
  deleteFile: vi.fn(),
  renameFile: vi.fn(),
  downloadFileBlob: vi.fn(),
}));

import * as filesApi from '../../api/files';
import { useFileBrowser } from '../../hooks/useFileBrowser';

const mp = { id: 'a', name: 'Main', type: 'raid', path: '/mnt/main', size_bytes: 100, used_bytes: 40, available_bytes: 60, status: 'ok', is_default: true };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(filesApi.getMountpoints).mockResolvedValue({ mountpoints: [mp] } as never);
  vi.mocked(filesApi.listFiles).mockResolvedValue({ files: [{ name: 'a.txt', path: 'a.txt', size: 1, type: 'file', modified_at: '2026-01-01T00:00:00Z' }] } as never);
  vi.mocked(filesApi.createFolder).mockResolvedValue({} as never);
  vi.mocked(filesApi.deleteFile).mockResolvedValue({} as never);
  vi.mocked(filesApi.renameFile).mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe('useFileBrowser', () => {
  it('auto-selects the default mountpoint and lists its root', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    expect(result.current.currentPath).toBe('');
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    expect(filesApi.listFiles).toHaveBeenCalledWith('/mnt/main');
    expect(result.current.files[0].name).toBe('a.txt');
    expect(result.current.storageInfo).toEqual({ totalBytes: 100, usedBytes: 40, availableBytes: 60 });
  });

  it('does not list before a mountpoint is selected', async () => {
    vi.mocked(filesApi.getMountpoints).mockResolvedValue({ mountpoints: [] } as never);
    renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await act(async () => { await Promise.resolve(); });
    expect(filesApi.listFiles).not.toHaveBeenCalled();
  });

  it('navigateToFolder re-lists the new full path', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    act(() => result.current.navigateToFolder('/mnt/main/docs'));
    await waitFor(() => expect(result.current.currentPath).toBe('docs'));
    await waitFor(() => expect(filesApi.listFiles).toHaveBeenCalledWith('/mnt/main/docs'));
  });

  it('createFolder posts and invalidates the listing', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    expect(filesApi.listFiles).toHaveBeenCalledTimes(1);
    let ok = false;
    await act(async () => { ok = await result.current.createFolder('New'); });
    expect(ok).toBe(true);
    expect(filesApi.createFolder).toHaveBeenCalledWith({ path: '/mnt/main', name: 'New' });
    await waitFor(() => expect(filesApi.listFiles).toHaveBeenCalledTimes(2));
  });

  it('createFolder rejects an empty name without calling the API', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    let ok = true;
    await act(async () => { ok = await result.current.createFolder('   '); });
    expect(ok).toBe(false);
    expect(filesApi.createFolder).not.toHaveBeenCalled();
  });

  it('deleteFile and renameFile call the API with the file path', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    await act(async () => { await result.current.deleteFile(result.current.files[0]); });
    expect(filesApi.deleteFile).toHaveBeenCalledWith('a.txt');
    await act(async () => { await result.current.renameFile(result.current.files[0], 'b.txt'); });
    expect(filesApi.renameFile).toHaveBeenCalledWith({ old_path: 'a.txt', new_name: 'b.txt' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/hooks/useFileBrowser.test.tsx`
Expected: FAIL — cannot resolve `../../hooks/useFileBrowser`.

- [ ] **Step 3: Create the hook**

Create `client/src/hooks/useFileBrowser.ts`:

```ts
import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import {
  getMountpoints,
  listFiles,
  createFolder as apiCreateFolder,
  deleteFile as apiDeleteFile,
  renameFile as apiRenameFile,
  downloadFileBlob,
} from '../api/files';
import { getFullPath, mapApiFileItem, parentPath, toRelativePath } from '../components/file-manager/utils';
import type { FileItem, StorageInfo, StorageMountpoint } from '../components/file-manager/types';

const getErrorMessage = (error: unknown): string => {
  if (!error || typeof error !== 'object') return 'Unknown error';
  const obj = error as Record<string, unknown>;
  return String(obj.error ?? obj.detail ?? 'Unknown error');
};
const errDetail = (err: unknown) => (err as { response?: { data?: unknown } })?.response?.data ?? err;

export interface UseFileBrowserResult {
  mountpoints: StorageMountpoint[];
  selectedMountpoint: StorageMountpoint | null;
  selectMountpoint: (mp: StorageMountpoint) => void;
  currentPath: string;
  getFullPath: (path?: string) => string;
  navigateToFolder: (folderPath: string) => void;
  goBack: () => void;
  goHome: () => void;
  files: FileItem[];
  loading: boolean;
  storageInfo: StorageInfo | null;
  createFolder: (name: string) => Promise<boolean>;
  deleteFile: (file: FileItem) => Promise<boolean>;
  renameFile: (file: FileItem, newName: string) => Promise<boolean>;
  downloadFile: (file: FileItem) => Promise<void>;
  refresh: () => void;
}

export function useFileBrowser(): UseFileBrowserResult {
  const { t } = useTranslation(['fileManager', 'common']);
  const queryClient = useQueryClient();
  const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
  const [currentPath, setCurrentPath] = useState('');

  const mountpointsQuery = useQuery({ queryKey: queryKeys.files.mountpoints(), queryFn: getMountpoints });

  // Auto-select the default mountpoint once loaded (matches the old loadMountpoints()).
  useEffect(() => {
    if (selectedMountpoint || !mountpointsQuery.data) return;
    const mps = mountpointsQuery.data.mountpoints;
    const def = mps.find((mp) => mp.is_default) ?? mps[0];
    if (def) {
      setSelectedMountpoint(def);
      setCurrentPath('');
    }
  }, [mountpointsQuery.data, selectedMountpoint]);

  // Preserve the original toast on a mountpoints load failure.
  useEffect(() => {
    if (mountpointsQuery.isError) toast.error('Failed to load storage devices');
  }, [mountpointsQuery.isError]);

  const resolveFullPath = useCallback(
    (path: string = currentPath) => getFullPath(selectedMountpoint, path),
    [selectedMountpoint, currentPath],
  );
  const fullPath = resolveFullPath();

  const filesQuery = useQuery({
    queryKey: queryKeys.files.list(fullPath),
    queryFn: async () => {
      const data = await listFiles(fullPath);
      return Array.isArray(data.files) ? data.files.map(mapApiFileItem) : [];
    },
    enabled: !!selectedMountpoint,
  });

  const files = filesQuery.data ?? [];
  const loading = filesQuery.isFetching;

  const storageInfo: StorageInfo | null = selectedMountpoint
    ? {
        totalBytes: selectedMountpoint.size_bytes,
        usedBytes: selectedMountpoint.used_bytes,
        availableBytes: selectedMountpoint.available_bytes,
      }
    : null;

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.files.list(fullPath) });
  }, [queryClient, fullPath]);

  const selectMountpoint = useCallback((mp: StorageMountpoint) => {
    setSelectedMountpoint(mp);
    setCurrentPath('');
  }, []);

  const navigateToFolder = useCallback(
    (folderPath: string) => setCurrentPath(toRelativePath(selectedMountpoint, folderPath)),
    [selectedMountpoint],
  );
  const goBack = useCallback(() => setCurrentPath((p) => parentPath(p)), []);
  const goHome = useCallback(() => setCurrentPath(''), []);

  const createFolder = useCallback(
    async (name: string): Promise<boolean> => {
      if (!name.trim()) {
        toast.error(t('fileManager:messages.enterFolderName', 'Please enter a folder name'));
        return false;
      }
      try {
        await apiCreateFolder({ path: resolveFullPath(), name });
        toast.success(t('fileManager:messages.folderCreated', 'Folder created successfully'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.folderError', 'Failed to create folder')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, resolveFullPath, refresh],
  );

  const deleteFile = useCallback(
    async (file: FileItem): Promise<boolean> => {
      try {
        await apiDeleteFile(file.path);
        toast.success(t('fileManager:messages.deleteSuccess'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.deleteError')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, refresh],
  );

  const renameFile = useCallback(
    async (file: FileItem, newName: string): Promise<boolean> => {
      if (!newName.trim()) {
        toast.error(t('fileManager:messages.enterFileName', 'Please enter a valid file name'));
        return false;
      }
      try {
        await apiRenameFile({ old_path: file.path, new_name: newName });
        toast.success(t('fileManager:messages.renameSuccess'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.renameError')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, refresh],
  );

  const downloadFile = useCallback(
    async (file: FileItem): Promise<void> => {
      if (file.type === 'directory') return;
      try {
        const blob = await downloadFileBlob(file.path);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch {
        toast.error(t('fileManager:messages.downloadError', 'Download failed'));
      }
    },
    [t],
  );

  return {
    mountpoints: mountpointsQuery.data?.mountpoints ?? [],
    selectedMountpoint,
    selectMountpoint,
    currentPath,
    getFullPath: resolveFullPath,
    navigateToFolder,
    goBack,
    goHome,
    files,
    loading,
    storageInfo,
    createFolder,
    deleteFile,
    renameFile,
    downloadFile,
    refresh,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/hooks/useFileBrowser.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useFileBrowser.ts client/src/__tests__/hooks/useFileBrowser.test.tsx
git commit -m "feat(files): add useFileBrowser query-backed browsing hook (#301)"
```

---

### Task 4: Wire `useFileBrowser` into `FileManager.tsx` + verify

**Files:**
- Modify: `client/src/pages/FileManager.tsx`
- Modify: `client/src/hooks/CLAUDE.md`

**Interfaces:**
- Consumes: `useFileBrowser` (Task 3).

- [ ] **Step 1: Add the hook and remove the migrated browser-core code**

In `client/src/pages/FileManager.tsx`:

1. Add the import next to the other hook imports:
```tsx
import { useFileBrowser } from '../hooks/useFileBrowser';
```
2. At the top of the component (with the other hooks, before `if (!user) return null`), add:
```tsx
  const {
    mountpoints, selectedMountpoint, selectMountpoint,
    currentPath, getFullPath, navigateToFolder, goBack, goHome,
    files, loading, storageInfo,
    createFolder, deleteFile, renameFile, downloadFile, refresh,
  } = useFileBrowser();
```
3. **Remove** these `useState` lines (now owned by the hook): `files`, `currentPath`, `loading`, `storageInfo`, `mountpoints`, `selectedMountpoint` (the `:84-99` subset — keep `userCache`, the dialog state `showNewFolderDialog`/`newFolderName`/`showDeleteDialog`/`fileToDelete`/`showRenameDialog`/`fileToRename`/`newFileName`, `dragActive`, `viewingFile`, `fileInputRef`, `folderInputRef`).
4. **Remove** the local functions now on the hook: `loadMountpoints` (`:271-285`), `loadStorageInfo` (`:287-296`), `getFullPath` (`:298-307`), `loadFiles` (`:309-362`), `handleDownload` (`:378-396`), `handleCreateFolder` (`:398-418`), `handleDelete` (`:425-441`), `handleRename` (`:449-470`), the local `navigateToFolder` (`:547-557`), the local `goBack` (`:559-564`), and the local `getErrorMessage` (`:117-121`, only used by the three removed handlers).
5. **Remove** the browser-core effects: the `[currentPath, selectedMountpoint]` load effect (`:141-146`) entirely; and drop `loadMountpoints()` from the mount effect (`:123-127`) so it becomes:
```tsx
  useEffect(() => {
    loadVclQuota();
    loadUserRootUsage();
  }, []);
```
6. **Rewrite** the `onUploadsComplete` effect (`:130-139`) to use `refresh()` and drop the dead sessionStorage/`loadStorageInfo` lines:
```tsx
  useEffect(() => {
    return onUploadsComplete(() => {
      refresh();
      loadVclQuota();
      loadUserRootUsage();
    });
  }, [onUploadsComplete, refresh]);
```
7. **Rewire** the render/handlers (only these — leave everything else, incl. VCL/upload/permission/ownership/share, untouched):
   - `StorageSelector` `onSelect`: `(mp) => { setSelectedMountpoint(mp); setCurrentPath(''); }` → `selectMountpoint`.
   - Breadcrumb **Home** button (`:754-759`): `onClick={() => setCurrentPath('')}` → `onClick={goHome}`. **Back** button (`:763-768`): `onClick={goBack}` (unchanged name, now the hook's).
   - `FileListView`: `onNavigate={navigateToFolder}`, `onDownload={downloadFile}` (both now the hook's — same names, no change needed), and `files={files}` / `loading={loading}` now come from the hook.
   - `NewFolderDialog` `onCreate`: replace `handleCreateFolder` with
     `onCreate={async () => { if (await createFolder(newFolderName)) { setShowNewFolderDialog(false); setNewFolderName(''); } }}`.
   - `DeleteDialog` `onConfirm`: replace `handleDelete` with
     `onConfirm={async () => { if (fileToDelete && await deleteFile(fileToDelete)) { setShowDeleteDialog(false); setFileToDelete(null); } }}`.
   - `RenameDialog` `onRename`: replace `handleRename` with
     `onRename={async () => { if (fileToRename && await renameFile(fileToRename, newFileName)) { setShowRenameDialog(false); setFileToRename(null); setNewFileName(''); } }}`.
   - `VersionHistoryModal` `onVersionRestored` (`:854-856`): `() => { loadFiles(currentPath, false); }` → `() => { refresh(); }`.
   - `OwnershipTransferModal` `onSuccess` (`:885-894`): change the trailing `loadFiles(currentPath, false);` to `refresh();` (leave the rest of that callback as-is).
8. **Leave unchanged** (they now read the hook's values via the destructure — same identifiers): `handleUpload`/`handleFolderUpload`/`handleDrop` (use `getFullPath()` + `storageInfo?.availableBytes`), `confirmDelete`/`startRename` (open dialogs), the `files`-driven effects (version-counts/tracking/owner-cache), and all VCL/permission/ownership/share handlers.

- [ ] **Step 2: Build (typecheck) — fix any dangling references**

Run: `cd client ; npm run build`
Expected: `✓ built` (tsc -b + vite), no `error TS`. If tsc flags an unused import (e.g. `apiClient` if no longer referenced — note `apiClient` is still used by nothing after removal? verify: it was used by loadMountpoints/loadFiles/handleDownload/create/delete/rename — all removed, so `apiClient` import is now dead → remove it) or an unused symbol, remove exactly the dead ones it names.

> Likely now-dead imports to remove from `FileManager.tsx`: `apiClient` (all its uses moved to the hook/api); and from the `../components/file-manager/types` import, `StorageInfo`, `StorageMountpoint`, and `ApiFileItem` are now only used inside the hook (the page's `selectedMountpoint`/`storageInfo` are typed via the hook's return) — trim the type import to `import type { FileItem, PermissionRule } from '../components/file-manager/types'`. Keep everything still referenced by PR-2 code (`getFilePermissions`/`setFilePermissions`/`getUserRootUsage`, `vclApi`/tracking fns, `getShareableUsers`, the icons, `formatBytes`/`formatNumber`, all modal components, `FileItem`/`PermissionRule` types). Let tsc/eslint be the final authority on exactly which to remove.

- [ ] **Step 3: Lint**

Run: `cd client ; npx eslint .`
Expected: 0 errors. Remove any unused-var/import the linter names (dead code from the removal), nothing else.

- [ ] **Step 4: Full test suite**

Run: `cd client ; npx vitest run`
Expected: all green — the prior suite + the new `utils.test.ts` (helpers) and `useFileBrowser.test.tsx` (6). Report the exact file/test counts. If any pre-existing/unrelated test fails, report it (name + output) as DONE_WITH_CONCERNS rather than fixing out-of-scope code.

- [ ] **Step 5: Update `hooks/CLAUDE.md`**

Add a row to the Data Fetching Hooks table in `client/src/hooks/CLAUDE.md` for `useFileBrowser.ts` (api module `api/files`): browsing core for `FileManager` via TanStack Query — mountpoints + directory listing (`files.list(fullPath)` key), navigation, derived `storageInfo`, and create/delete/rename mutations that invalidate the listing; replaces the page's hand-rolled `sessionStorage` file cache (F2/#301, PR-1). Keep it one line, matching the table's style.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/FileManager.tsx client/src/hooks/CLAUDE.md
git commit -m "refactor(files): FileManager browsing core via useFileBrowser (#301)"
```

---

## Notes for the implementer

- This is PR-1 of two. Do **not** touch VCL (quota, user-root-usage, version-counts, tracking + toggle), upload/drag-drop, or the permission/ownership/share modals — they stay and keep reading the hook's `files`/`currentPath`/`getFullPath`/`storageInfo`. The page will still be ~700 lines after this PR; PR-2 finishes the job.
- The only intended behavior change is the cache mechanism (manual `sessionStorage` → TanStack Query + app-wide persister). Everything else — listings, navigation, CRUD toasts, refetch-after-mutation — must be identical.
- Line numbers are from `FileManager.tsx` at 914 lines. If edits shift them, match on the quoted markers (`{/* Storage Drive Selector */}`, `{/* Breadcrumb Navigation */}`, `{/* New Folder Dialog */}`, etc.) and the function names.
- After Task 3, `useFileBrowser` is not yet imported anywhere — expected; it is covered by its own test. Only Task 4 wires it into the page.
