# F2 — FileManager VCL + Upload Extraction (PR-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the VCL slice and upload/drag-drop logic out of `FileManager.tsx` (700 → ~470 lines) into `useVclFileInfo` + `useFileUpload` hooks plus pure helpers, finishing the page as a composition root under the F2 500-line convention.

**Architecture:** `useVclFileInfo(files)` owns the VCL slice — quota + user-root-usage as `useQuery`, version-counts + tracking as effect-driven fan-outs (deliberate — see Global Constraints), a `toggleTracking` action, and `refreshVcl()`. `useFileUpload({getFullPath, availableBytes})` owns drag state + the upload handlers. Owner-name cache becomes a pure helper + `useMemo`. The page keeps the permission/ownership/share modal orchestration.

**Tech Stack:** React 18 + TypeScript, TanStack Query v5, react-hot-toast, Vitest + React Testing Library (`renderHook` + `createQueryWrapper`).

## Global Constraints

- **Behavior-preserving except the two simple VCL reads (quota, user-root-usage) moving to TanStack Query.** Same version-counts, same tracking, same toggle toasts, same quota warning/critical toasts, same upload behavior.
- **DELIBERATE DESIGN DECISION — VCL fan-outs stay effect-based.** `versionCounts` (`vclApi.getFileVersions` per file) and `trackingStatus`/`vclMode` (`getTrackingRules` + `checkFileTracking` per file) are moved **verbatim as `useEffect` + `Promise.all` into the hook — NOT migrated to `useQuery`**. They are N+1 fan-outs with per-file partial-failure tolerance, page-scoped (no cross-mount dedup benefit), and would need array-of-file-id keys. This is intentional, recorded in the spec; do not "consistency-migrate" them to Query.
- `toggleTracking` stays **optimistic** (flips `trackingStatus` locally + calls the add/remove-rule API, no refetch) — exactly as the original `handleToggleTracking`.
- Quota + user-root-usage query errors are **silently swallowed** (matches the original `catch {}`). The quota warning/critical **toast** fires from an effect on the quota data (preserves the mount + post-upload toast). **Intentional nuance (spec-sanctioned, do NOT flag as a regression):** keying the toast on `quotaQuery.data` means TanStack's structural sharing suppresses a *re-toast when the refetched value is byte-identical* — whereas the old `loadVclQuota` re-fired unconditionally on every call. A real upload changes usage → the toast still fires; only a zero-delta refetch is now quiet. This is a minor de-dup improvement, not lost behavior.
- No UX/layout change. No new dependencies.
- Hooks call typed `api/*` functions (`vclApi`, `api/files.getUserRootUsage`), not `apiClient` directly.
- Test pattern: `renderHook` + `createQueryWrapper` from `src/__tests__/helpers/queryClient`; pure helpers get plain unit tests.
- Windows shell: chain with `;`, never `&&`.
- Out of scope: the permission/ownership/share modals + handlers, `useFileBrowser`, all presentational components.

---

### Task 1: Pure helpers `vclWarningLevel` + `buildOwnerNameCache`

**Files:**
- Modify: `client/src/components/file-manager/utils.ts` (append)
- Modify: `client/src/__tests__/components/file-manager/utils.test.ts` (append)

**Interfaces:**
- Produces:
  - `vclWarningLevel(usagePercent: number): 'warning' | 'critical' | null`
  - `buildOwnerNameCache(files: FileItem[]): Record<string, string>`

- [ ] **Step 1: Append the failing tests**

Append to `client/src/__tests__/components/file-manager/utils.test.ts` (add `vclWarningLevel, buildOwnerNameCache` to the existing import from `../../../components/file-manager/utils`, and `FileItem` to the existing type import):

```ts
describe('vclWarningLevel', () => {
  it('returns critical at or above 95%', () => {
    expect(vclWarningLevel(95)).toBe('critical');
    expect(vclWarningLevel(99.9)).toBe('critical');
  });
  it('returns warning in [80, 95)', () => {
    expect(vclWarningLevel(80)).toBe('warning');
    expect(vclWarningLevel(94.9)).toBe('warning');
  });
  it('returns null below 80%', () => {
    expect(vclWarningLevel(79.9)).toBeNull();
    expect(vclWarningLevel(0)).toBeNull();
  });
});

describe('buildOwnerNameCache', () => {
  const f = (over: Partial<FileItem>): FileItem => ({
    name: 'x', path: 'x', size: 0, type: 'file', modifiedAt: 't', ...over,
  });
  it('maps ownerId -> ownerName for valid entries', () => {
    const cache = buildOwnerNameCache([f({ ownerId: 7, ownerName: 'bob' }), f({ ownerId: 9, ownerName: 'ann' })]);
    expect(cache).toEqual({ '7': 'bob', '9': 'ann' });
  });
  it('skips missing / "null" / absent owner names', () => {
    const cache = buildOwnerNameCache([
      f({ ownerId: 1, ownerName: undefined }),
      f({ ownerId: 2, ownerName: 'null' }),
      f({ ownerName: 'noid' }),
    ]);
    expect(cache).toEqual({});
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd client ; npx vitest run src/__tests__/components/file-manager/utils.test.ts`
Expected: FAIL — `vclWarningLevel` / `buildOwnerNameCache` are not exported.

- [ ] **Step 3: Append the implementations to `utils.ts`**

Append to `client/src/components/file-manager/utils.ts` (`FileItem` is already imported there):

```ts
/** VCL quota warning level: >=95 critical, >=80 warning, else null. */
export function vclWarningLevel(usagePercent: number): 'warning' | 'critical' | null {
  if (usagePercent >= 95) return 'critical';
  if (usagePercent >= 80) return 'warning';
  return null;
}

/** Derives the ownerId->ownerName cache from the backend-provided owner_name field. */
export function buildOwnerNameCache(files: FileItem[]): Record<string, string> {
  const cache: Record<string, string> = {};
  for (const f of files) {
    if (f.ownerId != null && f.ownerName && f.ownerName !== 'null') {
      cache[f.ownerId] = f.ownerName;
    }
  }
  return cache;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd client ; npx vitest run src/__tests__/components/file-manager/utils.test.ts`
Expected: PASS (prior 10 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/file-manager/utils.ts client/src/__tests__/components/file-manager/utils.test.ts
git commit -m "refactor(files): add vclWarningLevel + buildOwnerNameCache helpers (#301)"
```

---

### Task 2: `useVclFileInfo` hook

**Files:**
- Modify: `client/src/lib/queryKeys.ts`
- Create: `client/src/hooks/useVclFileInfo.ts`
- Test: `client/src/__tests__/hooks/useVclFileInfo.test.tsx`

**Interfaces:**
- Consumes: `vclWarningLevel` (Task 1), `vclApi`, `getUserRootUsage`, new query keys.
- Produces: `useVclFileInfo(files: FileItem[]): UseVclFileInfoResult` (surface in the code below).

- [ ] **Step 1: Add the query keys**

In `client/src/lib/queryKeys.ts`: add `userRootUsage` to the existing `files` block, and a new `vcl` block:

```ts
  files: {
    all: () => ['files'] as const,
    mountpoints: () => ['files', 'mountpoints'] as const,
    list: (fullPath: string) => ['files', 'list', fullPath] as const,
    userRootUsage: () => ['files', 'user-root-usage'] as const,
  },
  vcl: {
    quota: () => ['vcl', 'quota'] as const,
  },
```

- [ ] **Step 2: Write the failing test**

Create `client/src/__tests__/hooks/useVclFileInfo.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { FileItem } from '../../components/file-manager/types';

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock('../../api/vcl', () => ({
  vclApi: { getUserQuota: vi.fn(), getFileVersions: vi.fn() },
  getTrackingRules: vi.fn(),
  addTrackingRule: vi.fn(),
  removeTrackingRule: vi.fn(),
  checkFileTracking: vi.fn(),
}));
vi.mock('../../api/files', () => ({ getUserRootUsage: vi.fn() }));

import { vclApi, getTrackingRules, addTrackingRule, checkFileTracking } from '../../api/vcl';
import { getUserRootUsage } from '../../api/files';
import { useVclFileInfo } from '../../hooks/useVclFileInfo';

const file = (over: Partial<FileItem>): FileItem => ({ name: 'x', path: 'x', size: 0, type: 'file', modifiedAt: 't', ...over });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(vclApi.getUserQuota).mockResolvedValue({ usage_percent: 82, current_usage_bytes: 82, max_size_bytes: 100 } as never);
  vi.mocked(getUserRootUsage).mockResolvedValue({ user_root_used_bytes: 500 } as never);
  vi.mocked(vclApi.getFileVersions).mockResolvedValue({ total: 3 } as never);
  vi.mocked(getTrackingRules).mockResolvedValue({ mode: 'manual', rules: [] } as never);
  vi.mocked(checkFileTracking).mockResolvedValue({ is_tracked: true } as never);
  vi.mocked(addTrackingRule).mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe('useVclFileInfo', () => {
  it('maps quota to vclQuota with a warning level and exposes user-root usage', async () => {
    const { result } = renderHook(() => useVclFileInfo([]), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.vclQuota).not.toBeNull());
    expect(result.current.vclQuota).toEqual({ usagePercent: 82, warning: 'warning', current: 82, max: 100 });
    await waitFor(() => expect(result.current.userRootUsageBytes).toBe(500));
  });

  it('loads version counts for files with a file_id (fan-out)', async () => {
    const files = [file({ file_id: 11 }), file({ file_id: 22 })];
    const { result } = renderHook(() => useVclFileInfo(files), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.versionCounts[11]).toBe(3));
    expect(vclApi.getFileVersions).toHaveBeenCalledWith(11);
    expect(result.current.versionCounts[22]).toBe(3);
  });

  it('toggleTracking (manual mode, currently tracked) adds an exclude rule and flips status', async () => {
    const f = file({ file_id: 11, name: 'doc' });
    const { result } = renderHook(() => useVclFileInfo([f]), { wrapper: createQueryWrapper() });
    // manual mode + checkFileTracking is_tracked:true => trackingStatus[11] true
    await waitFor(() => expect(result.current.trackingStatus[11]).toBe(true));
    await act(async () => { await result.current.toggleTracking(f); });
    // manual + currently tracked => removeTrackingRule path needs a matching rule; none here,
    // so it just flips optimistically to false.
    expect(result.current.trackingStatus[11]).toBe(false);
  });
});
```

> Note: `getFileVersions` is called by the hook as `vclApi.getFileVersions(fileId)` (single arg — the `limit`/`offset` defaults apply). The `toggleTracking` test exercises the manual-mode "currently tracked" branch (which flips to false); the add-exclude branch is `automatic` mode.

- [ ] **Step 3: Run to verify failure**

Run: `cd client ; npx vitest run src/__tests__/hooks/useVclFileInfo.test.tsx`
Expected: FAIL — cannot resolve `../../hooks/useVclFileInfo`.

- [ ] **Step 4: Create the hook**

Create `client/src/hooks/useVclFileInfo.ts`:

```ts
import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import { formatBytes, formatNumber } from '../lib/formatters';
import {
  vclApi,
  addTrackingRule,
  removeTrackingRule,
  getTrackingRules,
  checkFileTracking,
} from '../api/vcl';
import { getUserRootUsage } from '../api/files';
import { vclWarningLevel } from '../components/file-manager/utils';
import type { FileItem } from '../components/file-manager/types';

export interface VclQuota {
  usagePercent: number;
  warning: 'warning' | 'critical' | null;
  current: number;
  max: number;
}

export interface UseVclFileInfoResult {
  vclQuota: VclQuota | null;
  userRootUsageBytes: number | null;
  versionCounts: Record<number, number>;
  trackingStatus: Record<number, boolean>;
  vclMode: 'automatic' | 'manual';
  toggleTracking: (file: FileItem) => Promise<void>;
  refreshVcl: () => void;
}

export function useVclFileInfo(files: FileItem[]): UseVclFileInfoResult {
  const queryClient = useQueryClient();
  const [versionCounts, setVersionCounts] = useState<Record<number, number>>({});
  const [trackingStatus, setTrackingStatus] = useState<Record<number, boolean>>({});
  const [vclMode, setVclMode] = useState<'automatic' | 'manual'>('automatic');

  const quotaQuery = useQuery({ queryKey: queryKeys.vcl.quota(), queryFn: vclApi.getUserQuota });
  const rootUsageQuery = useQuery({ queryKey: queryKeys.files.userRootUsage(), queryFn: getUserRootUsage });

  const quota = quotaQuery.data;
  const vclQuota: VclQuota | null = quota
    ? {
        usagePercent: quota.usage_percent,
        warning: vclWarningLevel(quota.usage_percent),
        current: quota.current_usage_bytes,
        max: quota.max_size_bytes,
      }
    : null;

  // Preserve the original loadVclQuota() warning/critical toast, now on quota data change.
  useEffect(() => {
    if (!quota) return;
    const level = vclWarningLevel(quota.usage_percent);
    if (level === 'critical') {
      toast.error(
        `VCL Storage Critical: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
        { duration: 8000 },
      );
    } else if (level === 'warning') {
      toast(
        `VCL Storage Warning: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
        { duration: 6000, icon: '⚠️' },
      );
    }
  }, [quota]);

  const userRootUsageBytes = rootUsageQuery.data?.user_root_used_bytes ?? null;

  // Version counts for files with a file_id (effect-based fan-out — deliberate, see plan).
  useEffect(() => {
    const loadVersionCounts = async () => {
      const fileIds = files.filter((f) => f.type === 'file' && f.file_id).map((f) => f.file_id!);
      if (fileIds.length === 0) return;
      try {
        const counts: Record<number, number> = {};
        await Promise.all(
          fileIds.map(async (fileId) => {
            try {
              const response = await vclApi.getFileVersions(fileId);
              counts[fileId] = response.total;
            } catch {
              // Ignore errors for individual files
            }
          }),
        );
        setVersionCounts(counts);
      } catch {
        // Ignore
      }
    };
    loadVersionCounts();
  }, [files]);

  // VCL mode + tracking status (effect-based fan-out — deliberate, see plan).
  useEffect(() => {
    const loadTrackingInfo = async () => {
      try {
        const rules = await getTrackingRules();
        setVclMode(rules.mode as 'automatic' | 'manual');
        const status: Record<number, boolean> = {};
        for (const rule of rules.rules) {
          if (rule.file_id) status[rule.file_id] = rule.action === 'track';
        }
        const fileIds = files.filter((f) => f.file_id).map((f) => f.file_id!);
        if (fileIds.length > 0 && fileIds.length <= 50) {
          await Promise.all(
            fileIds.map(async (fid) => {
              if (status[fid] !== undefined) return;
              try {
                const check = await checkFileTracking(fid);
                status[fid] = check.is_tracked;
              } catch {
                /* ignore */
              }
            }),
          );
        }
        setTrackingStatus(status);
      } catch {
        // Silently ignore
      }
    };
    if (files.length > 0) loadTrackingInfo();
  }, [files]);

  const toggleTracking = useCallback(
    async (file: FileItem) => {
      if (!file.file_id) return;
      const isCurrentlyTracked = trackingStatus[file.file_id] ?? (vclMode !== 'manual');
      try {
        if (isCurrentlyTracked) {
          if (vclMode === 'manual') {
            const rules = await getTrackingRules();
            const rule = rules.rules.find((r) => r.file_id === file.file_id && r.action === 'track');
            if (rule) await removeTrackingRule(rule.id);
          } else {
            await addTrackingRule({ file_id: file.file_id, action: 'exclude', is_directory: file.type === 'directory' });
          }
          setTrackingStatus((prev) => ({ ...prev, [file.file_id!]: false }));
          toast.success(`VCL disabled for ${file.name}`);
        } else {
          if (vclMode === 'automatic') {
            const rules = await getTrackingRules();
            const rule = rules.rules.find((r) => r.file_id === file.file_id && r.action === 'exclude');
            if (rule) await removeTrackingRule(rule.id);
          } else {
            await addTrackingRule({ file_id: file.file_id, action: 'track', is_directory: file.type === 'directory' });
          }
          setTrackingStatus((prev) => ({ ...prev, [file.file_id!]: true }));
          toast.success(`VCL enabled for ${file.name}`);
        }
      } catch {
        toast.error('Failed to update tracking');
      }
    },
    [trackingStatus, vclMode],
  );

  const refreshVcl = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.vcl.quota() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.files.userRootUsage() });
  }, [queryClient]);

  return { vclQuota, userRootUsageBytes, versionCounts, trackingStatus, vclMode, toggleTracking, refreshVcl };
}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd client ; npx vitest run src/__tests__/hooks/useVclFileInfo.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add client/src/lib/queryKeys.ts client/src/hooks/useVclFileInfo.ts client/src/__tests__/hooks/useVclFileInfo.test.tsx
git commit -m "feat(files): add useVclFileInfo hook (quota/root-usage via Query, fan-outs effect-based) (#301)"
```

---

### Task 3: `useFileUpload` hook

**Files:**
- Create: `client/src/hooks/useFileUpload.ts`
- Test: `client/src/__tests__/hooks/useFileUpload.test.tsx`

**Interfaces:**
- Consumes: `useUpload()` (`startUpload`, `isUploading`).
- Produces: `useFileUpload(opts: { getFullPath: () => string; availableBytes?: number }): UseFileUploadResult`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useFileUpload.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const { startUpload } = vi.hoisted(() => ({ startUpload: vi.fn() }));
vi.mock('../../contexts/UploadContext', () => ({
  useUpload: () => ({ startUpload, isUploading: false }),
}));

import { useFileUpload } from '../../hooks/useFileUpload';

const changeEvent = (files: unknown) =>
  ({ target: { files, value: 'keep' } } as unknown as React.ChangeEvent<HTMLInputElement>);
const dragEvent = (type: string) =>
  ({ type, preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as React.DragEvent);

beforeEach(() => vi.clearAllMocks());

describe('useFileUpload', () => {
  it('handleUpload forwards files, target path and availableBytes to startUpload and clears the input', () => {
    const getFullPath = () => '/mnt/main/docs';
    const { result } = renderHook(() => useFileUpload({ getFullPath, availableBytes: 123 }));
    const fakeList = { length: 1 } as unknown as FileList;
    const ev = changeEvent(fakeList);
    act(() => result.current.handleUpload(ev));
    expect(startUpload).toHaveBeenCalledWith(fakeList, '/mnt/main/docs', 123);
    expect((ev.target as HTMLInputElement).value).toBe('');
  });

  it('handleUpload is a no-op when no files are selected', () => {
    const { result } = renderHook(() => useFileUpload({ getFullPath: () => '/x' }));
    act(() => result.current.handleUpload(changeEvent(null)));
    expect(startUpload).not.toHaveBeenCalled();
  });

  it('handleDrag toggles dragActive on enter/leave', () => {
    const { result } = renderHook(() => useFileUpload({ getFullPath: () => '/x' }));
    act(() => result.current.handleDrag(dragEvent('dragenter')));
    expect(result.current.dragActive).toBe(true);
    act(() => result.current.handleDrag(dragEvent('dragleave')));
    expect(result.current.dragActive).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd client ; npx vitest run src/__tests__/hooks/useFileUpload.test.tsx`
Expected: FAIL — cannot resolve `../../hooks/useFileUpload`.

- [ ] **Step 3: Create the hook**

Create `client/src/hooks/useFileUpload.ts`:

```ts
import { useCallback, useState } from 'react';
import { useUpload } from '../contexts/UploadContext';

export interface UseFileUploadResult {
  dragActive: boolean;
  isUploading: boolean;
  handleUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleFolderUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleDrag: (e: React.DragEvent) => void;
  handleDrop: (e: React.DragEvent) => Promise<void>;
}

async function traverseFileTree(item: FileSystemEntry, path = ''): Promise<File[]> {
  const files: File[] = [];
  if (item.isFile) {
    return new Promise((resolve) => {
      (item as FileSystemFileEntry).file((file: File) => {
        const newFile = new File([file], path + file.name, { type: file.type });
        Object.defineProperty(newFile, 'webkitRelativePath', { value: path + file.name, writable: false });
        resolve([newFile]);
      });
    });
  } else if (item.isDirectory) {
    const dirReader = (item as FileSystemDirectoryEntry).createReader();
    return new Promise((resolve) => {
      const readEntries = () => {
        dirReader.readEntries(async (entries: FileSystemEntry[]) => {
          if (entries.length === 0) {
            resolve(files);
          } else {
            for (const entry of entries) {
              const subFiles = await traverseFileTree(entry, path + item.name + '/');
              files.push(...subFiles);
            }
            readEntries();
          }
        });
      };
      readEntries();
    });
  }
  return files;
}

export function useFileUpload(opts: { getFullPath: () => string; availableBytes?: number }): UseFileUploadResult {
  const { getFullPath, availableBytes } = opts;
  const { startUpload, isUploading } = useUpload();
  const [dragActive, setDragActive] = useState(false);

  const handleUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) return;
      startUpload(fileList, getFullPath(), availableBytes);
      e.target.value = '';
    },
    [startUpload, getFullPath, availableBytes],
  );

  const handleFolderUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) return;
      startUpload(fileList, getFullPath(), availableBytes);
      e.target.value = '';
    },
    [startUpload, getFullPath, availableBytes],
  );

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      const items = e.dataTransfer.items;
      if (!items) return;
      const allFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i].webkitGetAsEntry();
        if (item) {
          const dropped = await traverseFileTree(item);
          allFiles.push(...dropped);
        }
      }
      if (allFiles.length > 0) {
        const dt = new DataTransfer();
        allFiles.forEach((file) => dt.items.add(file));
        startUpload(dt.files, getFullPath(), availableBytes);
      }
    },
    [startUpload, getFullPath, availableBytes],
  );

  return { dragActive, isUploading, handleUpload, handleFolderUpload, handleDrag, handleDrop };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd client ; npx vitest run src/__tests__/hooks/useFileUpload.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useFileUpload.ts client/src/__tests__/hooks/useFileUpload.test.tsx
git commit -m "feat(files): add useFileUpload hook (drag/drop + upload handlers) (#301)"
```

---

### Task 4: Wire the hooks into `FileManager.tsx` + verify

**Files:**
- Modify: `client/src/pages/FileManager.tsx`
- Modify: `client/src/hooks/CLAUDE.md`

**Interfaces:**
- Consumes: `useVclFileInfo` (Task 2), `useFileUpload` (Task 3), `buildOwnerNameCache` (Task 1).

- [ ] **Step 1: Wire the hooks and remove the migrated code**

In `client/src/pages/FileManager.tsx`:

1. Imports: add
```tsx
import { useMemo } from 'react'; // merge into the existing "react" import
import { useVclFileInfo } from '../hooks/useVclFileInfo';
import { useFileUpload } from '../hooks/useFileUpload';
import { buildOwnerNameCache } from '../components/file-manager/utils';
```
2. After the `useFileBrowser()` destructure, add:
```tsx
  const {
    vclQuota, userRootUsageBytes, versionCounts, trackingStatus, vclMode,
    toggleTracking, refreshVcl,
  } = useVclFileInfo(files);
  const {
    dragActive, isUploading, handleUpload, handleFolderUpload, handleDrag, handleDrop,
  } = useFileUpload({ getFullPath, availableBytes: storageInfo?.availableBytes });
  const userCache = useMemo(() => buildOwnerNameCache(files), [files]);
```
3. Keep `const { onUploadsComplete } = useUpload();` (still needed for the effect) — but drop `startUpload` and `isUploading` from that destructure (they now come from `useFileUpload`).
4. **Remove** the VCL state (`versionCounts`, `trackingStatus`, `vclMode`, `vclQuota`, `userRootUsageBytes`), the `userCache` state, the `dragActive` state.
5. **Remove** the mount effect that called `loadVclQuota(); loadUserRootUsage();` (the queries load on mount now), and change the `onUploadsComplete` effect body to `refresh(); refreshVcl();` (deps `[onUploadsComplete, refresh, refreshVcl]`).
6. **Remove** the functions now owned by hooks: `loadVclQuota`, `loadUserRootUsage`, the version-counts effect, the tracking-info effect, the owner-name-cache effect, `handleUpload`, `handleFolderUpload`, `handleDrag`, `traverseFileTree`, `handleDrop`, `handleToggleTracking`.
7. **Keep** in the page: `handleVersionHistory` + `showVersionHistory`/`versionHistoryFile` state; the permission/ownership/share handlers + state; `confirmDelete`/`startRename`/`handleViewFile`; `fileInputRef`/`folderInputRef`.
8. Rewire the render:
   - `FileListView`: `onToggleTracking={toggleTracking}` (was `handleToggleTracking`); `versionCounts`, `trackingStatus`, `vclMode`, `dragActive`, and the four drag handlers now come from the hooks (same identifiers — no change beyond the toggle rename).
   - Upload `<label>`s: `isUploading` now from `useFileUpload`; `onChange={handleUpload}` / `onChange={handleFolderUpload}` unchanged (now the hook's).
   - Header badges (`vclQuota`, `userRootUsageBytes`) unchanged (now from the hook).
9. **Remove** now-dead imports (let tsc/eslint confirm): from `../api/vcl` the whole line (`vclApi, addTrackingRule, removeTrackingRule, getTrackingRules, checkFileTracking` all moved to the hook); `getUserRootUsage` from `../api/files` (moved). **Keep** `getFilePermissions`/`setFilePermissions` (permission modal), `formatBytes`/`formatNumber` (header), the icons, `useUpload` (onUploadsComplete), `VersionHistoryModal`.

- [ ] **Step 2: Line count**

Run (PowerShell): `cd client ; (Get-Content src/pages/FileManager.tsx | Measure-Object -Line).Lines`
Expected: under 500 (target ~470).

- [ ] **Step 3: Build**

Run: `cd client ; npm run build`
Expected: `✓ built`, no `error TS`. Remove exactly the dead imports it names.

- [ ] **Step 4: Lint**

Run: `cd client ; npx eslint .`
Expected: 0 errors.

- [ ] **Step 5: Full suite**

Run: `cd client ; npx vitest run`
Expected: all green — prior suite + new `vclWarningLevel`/`buildOwnerNameCache` (6), `useVclFileInfo` (3), `useFileUpload` (3). Report exact counts. Any pre-existing/unrelated failure → report as DONE_WITH_CONCERNS, don't fix out-of-scope.

- [ ] **Step 6: Update `hooks/CLAUDE.md`**

Add two rows to the Data Fetching Hooks table for `useVclFileInfo.ts` (api `api/vcl`, `api/files`) and `useFileUpload.ts` (context `UploadContext`), noting the F2/#301 PR-2 extraction, the quota/root-usage-via-Query + effect-based fan-outs decision, and the drag/upload ownership. One line each.

- [ ] **Step 7: Commit**

```bash
git add client/src/pages/FileManager.tsx client/src/hooks/CLAUDE.md
git commit -m "refactor(files): FileManager VCL + upload via hooks, page under 500 (#301)"
```

---

## Notes for the implementer

- This is PR-2 (final) for FileManager. The **deliberate decision** to keep the VCL fan-outs (version-counts, tracking) effect-based is intentional — move them verbatim into `useVclFileInfo`, do NOT convert them to `useQuery`.
- Only intended behavior change: quota + user-root-usage reads become `useQuery` (persister-backed); everything else identical, including the quota warning/critical toast (now fired from an effect on the quota data) and the optimistic `toggleTracking`.
- Line numbers reference `FileManager.tsx` at 700 lines. If edits shift them, match on the quoted comment markers (`// Load VCL Quota`, `// Build owner name cache …`, `{/* Storage Drive Selector */}`) and the function names.
- Tasks 2–3 add hooks not yet imported anywhere — expected; covered by their own tests. Only Task 4 wires them.
