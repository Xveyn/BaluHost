# SharesPage F2 Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zerlege `client/src/pages/SharesPage.tsx` (898 Zeilen) in fokussierte, getestete Komponenten unter `components/shares/` und reduziere die Page auf < 250 Zeilen — behavior-preserving, plus Vitest-Abdeckung für jede neue Komponente.

**Architecture:** Neues Feature-Verzeichnis `components/shares/` (analog `components/power/` aus #301) mit reinen Präsentationskomponenten (Daten rein, Callbacks rein) + ein neuer Daten-Hook `hooks/useCloudExports.ts`. Die Page bleibt Orchestrator: UI-State, Filtern/Sortieren, Modals, Verdrahtung. Cloud-Exports bleiben bewusst auf `useState`+`useEffect` (kein TanStack).

**Tech Stack:** React 18 + TypeScript (strict), Tailwind, `react-i18next`, `@tanstack/react-query` (nur für die bestehende Share-Mutation + `useFileShares`), `lucide-react`, Vitest + `@testing-library/react`.

## Global Constraints

- **Behavior-preserving:** keine Änderung an Sharing-/Backend-Logik, Endpoints, Sortier-/Filter-Verhalten. Einzige bewusste optische Änderung: Empty-States nutzen künftig `ui/EmptyState` (gray-Normalisierung).
- **Kein TanStack für Cloud-Exports** — `useCloudExports` ist `useState`+`useEffect` (nutzer-getriggert, kein Poller). Rationale im Hook kommentieren (weicht bewusst von der hooks/CLAUDE.md-TanStack-Konvention ab).
- **Test-Konvention (Assessment T7): keine Tailwind-Klassen-Assertions.** Nutze `getByRole` / `getByText` / `getByTitle`. `react-i18next` wird gemockt zu `t: (k) => k` → Assertions gegen i18n-Key-Strings (inkl. `ns:`-Präfix, wo der Quellcode ihn nutzt).
- **i18n-Keys unverändert lassen** — exakt dieselben Key-Strings wie im Original (z. B. `shares:cloudExport.statusReady`, `permissions.read`), damit reale Übersetzungen greifen.
- **Windows/CRLF:** Repo läuft mit `core.autocrlf=true`; die Git-Warnung „LF will be replaced by CRLF" ist erwartbar, kein Fehler.
- Jede Datei in `components/shares/` bleibt < ~200 Zeilen.
- Verifikation am Ende: `npx vitest run` grün, `eslint .` 0 Fehler, `npm run build` grün.

**Alle Befehle laufen aus `client/`** (`cd client` zuerst).

---

### Task 1: `types.ts` + `sharesFormat.ts` (pure Fundamente)

**Files:**
- Create: `client/src/components/shares/types.ts`
- Create: `client/src/components/shares/sharesFormat.ts`
- Test: `client/src/__tests__/components/shares/sharesFormat.test.ts`

**Interfaces:**
- Produces:
  - `type SharesTab = 'shares' | 'shared-with-me' | 'cloud-exports'`
  - `interface SortProps { sortKey: string | null; sortDirection: SortDirection; onSort: (key: string) => void }` (`SortDirection` aus `hooks/useSortableTable`)
  - `formatDate(dateString: string | null, neverLabel: string): string`
  - `formatFileSize(bytes: number | null): string`
  - `getProviderLabel(job: CloudExportJob): string`

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/components/shares/sharesFormat.test.ts
import { describe, it, expect } from 'vitest';
import { formatDate, formatFileSize, getProviderLabel } from '../../../components/shares/sharesFormat';
import type { CloudExportJob } from '../../../api/cloud-export';

const job = (share_link: string | null): CloudExportJob =>
  ({ share_link } as CloudExportJob);

describe('sharesFormat', () => {
  it('formatDate returns the never-label for null', () => {
    expect(formatDate(null, 'NEVER')).toBe('NEVER');
  });

  it('formatDate renders a real date via toLocaleDateString', () => {
    expect(formatDate('2026-01-15T00:00:00Z', 'NEVER'))
      .toBe(new Date('2026-01-15T00:00:00Z').toLocaleDateString());
  });

  it('formatFileSize returns 0 B for null/zero', () => {
    expect(formatFileSize(null)).toBe('0 B');
    expect(formatFileSize(0)).toBe('0 B');
  });

  it('getProviderLabel maps known hosts', () => {
    expect(getProviderLabel(job('https://drive.google.com/x'))).toBe('Google Drive');
    expect(getProviderLabel(job('https://1drv.ms/x'))).toBe('OneDrive');
    expect(getProviderLabel(job('https://acme.sharepoint.com/x'))).toBe('OneDrive');
    expect(getProviderLabel(job('https://example.com/x'))).toBe('Cloud');
    expect(getProviderLabel(job(null))).toBe('Cloud');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/sharesFormat.test.ts`
Expected: FAIL — cannot find module `sharesFormat`.

- [ ] **Step 3: Write the implementations**

```ts
// client/src/components/shares/types.ts
import type { SortDirection } from '../../hooks/useSortableTable';

export type SharesTab = 'shares' | 'shared-with-me' | 'cloud-exports';

export interface SortProps {
  sortKey: string | null;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
}
```

```ts
// client/src/components/shares/sharesFormat.ts
import { formatBytes } from '../../lib/formatters';
import type { CloudExportJob } from '../../api/cloud-export';

/** Localized date or the caller-provided "never" label for null. */
export function formatDate(dateString: string | null, neverLabel: string): string {
  if (!dateString) return neverLabel;
  return new Date(dateString).toLocaleDateString();
}

export function formatFileSize(bytes: number | null): string {
  if (!bytes) return '0 B';
  return formatBytes(bytes);
}

export function getProviderLabel(job: CloudExportJob): string {
  if (job.share_link?.includes('drive.google')) return 'Google Drive';
  if (job.share_link?.includes('1drv.ms') || job.share_link?.includes('sharepoint')) return 'OneDrive';
  return 'Cloud';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/sharesFormat.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/types.ts client/src/components/shares/sharesFormat.ts client/src/__tests__/components/shares/sharesFormat.test.ts
git commit -m "feat(shares): extract pure sharesFormat helpers + shared types (F2)"
```

---

### Task 2: `PermissionBadges.tsx`

**Files:**
- Create: `client/src/components/shares/PermissionBadges.tsx`
- Test: `client/src/__tests__/components/shares/PermissionBadges.test.tsx`

**Interfaces:**
- Produces: `PermissionBadges(props: { canRead?: boolean; canWrite?: boolean; canDelete?: boolean; size?: 'sm' | 'md' })` — renders a fragment of 0–3 pills. `md` = desktop padding (`px-2.5 py-1`), `sm` = mobile padding (`px-2 py-0.5`). Keys: `permissions.read|write|delete` in the `shares` namespace.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/PermissionBadges.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PermissionBadges } from '../../../components/shares/PermissionBadges';

describe('PermissionBadges', () => {
  it('renders only the granted permissions', () => {
    render(<PermissionBadges canRead canDelete />);
    expect(screen.getByText('permissions.read')).toBeInTheDocument();
    expect(screen.getByText('permissions.delete')).toBeInTheDocument();
    expect(screen.queryByText('permissions.write')).toBeNull();
  });

  it('renders nothing when no permission is granted', () => {
    const { container } = render(<PermissionBadges />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders all three when all granted', () => {
    render(<PermissionBadges canRead canWrite canDelete />);
    expect(screen.getByText('permissions.read')).toBeInTheDocument();
    expect(screen.getByText('permissions.write')).toBeInTheDocument();
    expect(screen.getByText('permissions.delete')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/PermissionBadges.test.tsx`
Expected: FAIL — cannot find module `PermissionBadges`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/PermissionBadges.tsx
import { useTranslation } from 'react-i18next';

interface PermissionBadgesProps {
  canRead?: boolean;
  canWrite?: boolean;
  canDelete?: boolean;
  size?: 'sm' | 'md';
}

export function PermissionBadges({ canRead, canWrite, canDelete, size = 'md' }: PermissionBadgesProps) {
  const { t } = useTranslation('shares');
  const pad = size === 'sm' ? 'px-2 py-0.5' : 'px-2.5 py-1';
  return (
    <>
      {canRead && (
        <span className={`${pad} border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold`}>
          {t('permissions.read')}
        </span>
      )}
      {canWrite && (
        <span className={`${pad} border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold`}>
          {t('permissions.write')}
        </span>
      )}
      {canDelete && (
        <span className={`${pad} border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold`}>
          {t('permissions.delete')}
        </span>
      )}
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/PermissionBadges.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/PermissionBadges.tsx client/src/__tests__/components/shares/PermissionBadges.test.tsx
git commit -m "feat(shares): extract PermissionBadges (dedup 4x) (F2)"
```

---

### Task 3: `FileNameCell.tsx`

**Files:**
- Create: `client/src/components/shares/FileNameCell.tsx`
- Test: `client/src/__tests__/components/shares/FileNameCell.test.tsx`

**Interfaces:**
- Produces: `FileNameCell(props: { isDirectory: boolean; name: string | null; size?: number | null; folderLabel: string; variant?: 'table' | 'card'; className?: string })`. Renders icon + name + sub-label. `table` variant uses `<div>`s; `card` variant uses truncating `<p>`s. Sub-label = `folderLabel` when directory, else `formatFileSize(size)`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/FileNameCell.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FileNameCell } from '../../../components/shares/FileNameCell';

describe('FileNameCell', () => {
  it('shows the folder label for a directory', () => {
    render(<FileNameCell isDirectory name="Docs" folderLabel="FOLDER" />);
    expect(screen.getByText('Docs')).toBeInTheDocument();
    expect(screen.getByText('FOLDER')).toBeInTheDocument();
  });

  it('shows a formatted size for a file', () => {
    render(<FileNameCell isDirectory={false} name="a.txt" size={0} folderLabel="FOLDER" />);
    expect(screen.getByText('a.txt')).toBeInTheDocument();
    expect(screen.getByText('0 B')).toBeInTheDocument();
    expect(screen.queryByText('FOLDER')).toBeNull();
  });

  it('renders in card variant without crashing', () => {
    render(<FileNameCell isDirectory={false} name="b.txt" size={0} folderLabel="F" variant="card" />);
    expect(screen.getByText('b.txt')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/FileNameCell.test.tsx`
Expected: FAIL — cannot find module `FileNameCell`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/FileNameCell.tsx
import { Folder, File as FileIcon } from 'lucide-react';
import { formatFileSize } from './sharesFormat';

interface FileNameCellProps {
  isDirectory: boolean;
  name: string | null;   // FileShare.file_name is nullable
  size?: number | null;
  folderLabel: string;
  variant?: 'table' | 'card';
  className?: string;
}

export function FileNameCell({ isDirectory, name, size, folderLabel, variant = 'table', className = '' }: FileNameCellProps) {
  const icon = isDirectory
    ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
    : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />;
  const sub = isDirectory ? folderLabel : formatFileSize(size ?? null);

  if (variant === 'card') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        {icon}
        <div className="min-w-0">
          <p className="font-semibold text-white truncate">{name}</p>
          <p className="text-xs text-slate-400">{sub}</p>
        </div>
      </div>
    );
  }
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {icon}
      <div>
        <div className="font-semibold text-white">{name}</div>
        <div className="text-xs sm:text-sm text-slate-400 mt-0.5">{sub}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/FileNameCell.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/FileNameCell.tsx client/src/__tests__/components/shares/FileNameCell.test.tsx
git commit -m "feat(shares): extract FileNameCell (dedup 6x) (F2)"
```

---

### Task 4: `CloudStatusBadge.tsx`

**Files:**
- Create: `client/src/components/shares/CloudStatusBadge.tsx`
- Test: `client/src/__tests__/components/shares/CloudStatusBadge.test.tsx`

**Interfaces:**
- Produces: `CloudStatusBadge(props: { job: CloudExportJob })` — the status pill (from the old `getStatusBadge`), incl. the `uploading` percent calculation `Math.round(progress_bytes / file_size_bytes * 100)`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/CloudStatusBadge.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { CloudStatusBadge } from '../../../components/shares/CloudStatusBadge';
import type { CloudExportJob } from '../../../api/cloud-export';

// Full object (no partial `as` cast): all required fields present, then override.
const job = (over: Partial<CloudExportJob> = {}): CloudExportJob => ({
  id: 1, user_id: 1, connection_id: 1, source_path: '/f', file_name: 'f',
  is_directory: false, file_size_bytes: 100, cloud_folder: '/', cloud_path: null,
  share_link: null, link_type: 'view', status: 'pending', progress_bytes: 0,
  error_message: null, created_at: '2026-01-01T00:00:00Z', completed_at: null,
  expires_at: null, ...over,
});

describe('CloudStatusBadge', () => {
  it('renders the ready status key', () => {
    render(<CloudStatusBadge job={job({ status: 'ready' })} />);
    expect(screen.getByText('shares:cloudExport.statusReady')).toBeInTheDocument();
  });

  it('shows upload percent when uploading with a known size', () => {
    render(<CloudStatusBadge job={job({ status: 'uploading', progress_bytes: 50, file_size_bytes: 100 })} />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('falls back to the generic status text for unknown status', () => {
    // status is a closed union; force an out-of-union value to hit the default arm.
    render(<CloudStatusBadge job={{ ...job(), status: 'weird' as unknown as CloudExportJob['status'] }} />);
    expect(screen.getByText('weird')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/CloudStatusBadge.test.tsx`
Expected: FAIL — cannot find module `CloudStatusBadge`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/CloudStatusBadge.tsx
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import type { CloudExportJob } from '../../api/cloud-export';

export function CloudStatusBadge({ job }: { job: CloudExportJob }) {
  const { t } = useTranslation('shares');
  switch (job.status) {
    case 'ready':
      return <span className="px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusReady', 'Ready')}</span>;
    case 'uploading':
    case 'creating_link':
      return (
        <span className="px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-semibold inline-flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" />
          {job.status === 'uploading'
            ? (job.file_size_bytes
              ? `${Math.round((job.progress_bytes / job.file_size_bytes) * 100)}%`
              : t('shares:cloudExport.statusUploading', 'Uploading'))
            : t('shares:cloudExport.statusCreatingLink', 'Creating link')}
        </span>
      );
    case 'pending':
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusPending', 'Pending')}</span>;
    case 'failed':
      return <span className="px-2.5 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusFailed', 'Failed')}</span>;
    case 'revoked':
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-500 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusRevoked', 'Revoked')}</span>;
    default:
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{job.status}</span>;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/CloudStatusBadge.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/CloudStatusBadge.tsx client/src/__tests__/components/shares/CloudStatusBadge.test.tsx
git commit -m "feat(shares): extract CloudStatusBadge (F2)"
```

---

### Task 5: `useCloudExports.ts` hook

**Files:**
- Create: `client/src/hooks/useCloudExports.ts`
- Test: `client/src/__tests__/hooks/useCloudExports.test.ts`

**Interfaces:**
- Consumes: `api/cloud-export` (`listCloudExports`, `getCloudExportStatistics`, `revokeCloudExport`, `retryCloudExport`), `react-hot-toast`.
- Produces:
  ```ts
  interface UseCloudExportsResult {
    cloudExports: CloudExportJob[];
    cloudStats: CloudExportStatistics | null;
    loading: boolean;
    reload: () => Promise<void>;
    revoke: (jobId: number) => Promise<void>;   // API + reload + toast, NO confirm
    retry: (jobId: number) => Promise<void>;    // API + reload + toast
  }
  ```
  `revoke`/`retry` do NOT prompt — the page wraps `revoke` with `useConfirmDialog`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/hooks/useCloudExports.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/cloud-export', () => ({
  listCloudExports: vi.fn(),
  getCloudExportStatistics: vi.fn(),
  revokeCloudExport: vi.fn(),
  retryCloudExport: vi.fn(),
}));

import toast from 'react-hot-toast';
import { listCloudExports, getCloudExportStatistics, revokeCloudExport, retryCloudExport } from '../../api/cloud-export';
import { useCloudExports } from '../../hooks/useCloudExports';

beforeEach(() => {
  vi.clearAllMocks();
  (listCloudExports as any).mockResolvedValue([{ id: 1, status: 'ready' }]);
  (getCloudExportStatistics as any).mockResolvedValue({ active_exports: 1, total_exports: 1, total_upload_bytes: 0 });
});

describe('useCloudExports', () => {
  it('loads exports + stats on mount', async () => {
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.cloudExports).toHaveLength(1);
    expect(result.current.cloudStats?.active_exports).toBe(1);
  });

  it('revoke calls the API, reloads and toasts success', async () => {
    (revokeCloudExport as any).mockResolvedValue(undefined);
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.revoke(1); });
    expect(revokeCloudExport).toHaveBeenCalledWith(1);
    expect(listCloudExports).toHaveBeenCalledTimes(2); // mount + reload
    expect(toast.success).toHaveBeenCalled();
  });

  it('retry toasts error when the API rejects', async () => {
    (retryCloudExport as any).mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.retry(1); });
    expect(toast.error).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/hooks/useCloudExports.test.ts`
Expected: FAIL — cannot find module `useCloudExports`.

- [ ] **Step 3: Write the implementation**

```ts
// client/src/hooks/useCloudExports.ts
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  listCloudExports,
  getCloudExportStatistics,
  revokeCloudExport,
  retryCloudExport,
  type CloudExportJob,
  type CloudExportStatistics,
} from '../api/cloud-export';

export interface UseCloudExportsResult {
  cloudExports: CloudExportJob[];
  cloudStats: CloudExportStatistics | null;
  loading: boolean;
  reload: () => Promise<void>;
  revoke: (jobId: number) => Promise<void>;
  retry: (jobId: number) => Promise<void>;
}

/**
 * Cloud-export list/stats + revoke/retry actions.
 *
 * Deliberately NOT TanStack Query (unlike the hooks/CLAUDE.md convention):
 * cloud exports are user-triggered, low-frequency data with no background
 * polling — one-shot load on mount + explicit reload after an action.
 * revoke/retry do NOT prompt; the page wraps revoke with a confirm dialog.
 */
export function useCloudExports(): UseCloudExportsResult {
  const { t } = useTranslation(['shares']);
  const [cloudExports, setCloudExports] = useState<CloudExportJob[]>([]);
  const [cloudStats, setCloudStats] = useState<CloudExportStatistics | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [cExports, cStats] = await Promise.all([
        listCloudExports().catch(() => []),
        getCloudExportStatistics().catch(() => null),
      ]);
      setCloudExports(cExports);
      setCloudStats(cStats);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const revoke = useCallback(async (jobId: number) => {
    try {
      await revokeCloudExport(jobId);
      await reload();
      toast.success(t('shares:cloudExport.revoked', 'Cloud share revoked'));
    } catch {
      toast.error(t('shares:cloudExport.revokeFailed', 'Failed to revoke cloud share'));
    }
  }, [reload, t]);

  const retry = useCallback(async (jobId: number) => {
    try {
      await retryCloudExport(jobId);
      await reload();
      toast.success(t('shares:cloudExport.retryStarted', 'Retry started'));
    } catch {
      toast.error(t('shares:cloudExport.retryFailed', 'Retry failed'));
    }
  }, [reload, t]);

  return { cloudExports, cloudStats, loading, reload, revoke, retry };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/hooks/useCloudExports.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useCloudExports.ts client/src/__tests__/hooks/useCloudExports.test.ts
git commit -m "feat(shares): add useCloudExports hook (state+effect, no TanStack) (F2)"
```

---

### Task 6: `SharesStatCards.tsx`

**Files:**
- Create: `client/src/components/shares/SharesStatCards.tsx`
- Test: `client/src/__tests__/components/shares/SharesStatCards.test.tsx`

**Interfaces:**
- Consumes: `types.ts` (`SharesTab`), `ShareStatistics` (`api/shares`), `CloudExportStatistics` (`api/cloud-export`), `ui/StatCard`, `formatBytes`.
- Produces: `SharesStatCards(props: { activeTab: SharesTab; statistics: ShareStatistics | null; cloudStats: CloudExportStatistics | null })` — renders the shares stat pair on the non-cloud tabs (when `statistics`), the cloud stat pair on the cloud tab (when `cloudStats`), else nothing.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/SharesStatCards.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesStatCards } from '../../../components/shares/SharesStatCards';
import type { ShareStatistics } from '../../../api/shares';
import type { CloudExportStatistics } from '../../../api/cloud-export';

const stats: ShareStatistics = { active_file_shares: 3, total_file_shares: 5, files_shared_with_me: 2 };
const cloud: CloudExportStatistics = { active_exports: 1, total_exports: 4, failed_exports: 0, total_upload_bytes: 0 };

describe('SharesStatCards', () => {
  it('shows share stats on the shares tab', () => {
    render(<SharesStatCards activeTab="shares" statistics={stats} cloudStats={null} />);
    expect(screen.getByText('stats.userShares')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText('shares:cloudExport.activeShares')).toBeNull();
  });

  it('shows cloud stats on the cloud tab', () => {
    render(<SharesStatCards activeTab="cloud-exports" statistics={stats} cloudStats={cloud} />);
    expect(screen.getByText('shares:cloudExport.activeShares')).toBeInTheDocument();
    expect(screen.queryByText('stats.userShares')).toBeNull();
  });

  it('renders nothing without matching stats', () => {
    const { container } = render(<SharesStatCards activeTab="shares" statistics={null} cloudStats={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesStatCards.test.tsx`
Expected: FAIL — cannot find module `SharesStatCards`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/SharesStatCards.tsx
import { useTranslation } from 'react-i18next';
import { Users, Share2, Cloud } from 'lucide-react';
import { StatCard } from '../ui/StatCard';
import { formatBytes } from '../../lib/formatters';
import type { ShareStatistics } from '../../api/shares';
import type { CloudExportStatistics } from '../../api/cloud-export';
import type { SharesTab } from './types';

interface SharesStatCardsProps {
  activeTab: SharesTab;
  statistics: ShareStatistics | null;
  cloudStats: CloudExportStatistics | null;
}

export function SharesStatCards({ activeTab, statistics, cloudStats }: SharesStatCardsProps) {
  const { t } = useTranslation(['shares', 'common']);

  if (activeTab !== 'cloud-exports' && statistics) {
    return (
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('stats.userShares')}
          value={statistics.active_file_shares}
          subValue={t('stats.ofTotal', { total: statistics.total_file_shares })}
          color="purple"
          icon={<Users className="h-5 w-5 sm:h-6 sm:w-6 text-purple-400" />}
        />
        <StatCard
          label={t('stats.sharedWithMe')}
          value={statistics.files_shared_with_me}
          subValue={t('stats.filesAccessible')}
          color="amber"
          icon={<Share2 className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400" />}
        />
      </div>
    );
  }

  if (activeTab === 'cloud-exports' && cloudStats) {
    return (
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('shares:cloudExport.activeShares', 'Active Cloud Shares')}
          value={cloudStats.active_exports}
          subValue={t('stats.ofTotal', { total: cloudStats.total_exports })}
          color="blue"
          icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />}
        />
        <StatCard
          label={t('shares:cloudExport.uploadVolume', 'Upload Volume')}
          value={formatBytes(cloudStats.total_upload_bytes)}
          subValue={t('shares:cloudExport.totalUploaded', 'Total uploaded')}
          color="green"
          icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-green-400" />}
        />
      </div>
    );
  }

  return null;
}
```

> **Note:** If `tsc` reports the `StatCard` `value` prop rejects a `string` (for `formatBytes(...)`), check the existing `StatCard` prop type — the original page already passed `formatBytes(...)` here, so the type must already allow `string | number`. Do not change `StatCard`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesStatCards.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/SharesStatCards.tsx client/src/__tests__/components/shares/SharesStatCards.test.tsx
git commit -m "feat(shares): extract SharesStatCards (F2)"
```

---

### Task 7: `SharesTabBar.tsx`

**Files:**
- Create: `client/src/components/shares/SharesTabBar.tsx`
- Test: `client/src/__tests__/components/shares/SharesTabBar.test.tsx`

**Interfaces:**
- Consumes: `types.ts` (`SharesTab`).
- Produces: `SharesTabBar(props: { activeTab: SharesTab; onChange: (tab: SharesTab) => void })` — three tab buttons; clicking calls `onChange` with the tab key.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/SharesTabBar.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesTabBar } from '../../../components/shares/SharesTabBar';

describe('SharesTabBar', () => {
  it('renders a button per tab and reports clicks', () => {
    const onChange = vi.fn();
    render(<SharesTabBar activeTab="shares" onChange={onChange} />);
    // labels appear twice (full + short label); target the buttons by role
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[2]);
    expect(onChange).toHaveBeenCalledWith('cloud-exports');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesTabBar.test.tsx`
Expected: FAIL — cannot find module `SharesTabBar`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/SharesTabBar.tsx
import { useTranslation } from 'react-i18next';
import { Users, Share2, Cloud } from 'lucide-react';
import type { SharesTab } from './types';

interface SharesTabBarProps {
  activeTab: SharesTab;
  onChange: (tab: SharesTab) => void;
}

export function SharesTabBar({ activeTab, onChange }: SharesTabBarProps) {
  const { t } = useTranslation(['shares', 'common']);
  const tabs = [
    { key: 'shares' as const, label: t('tabs.userShares'), shortLabel: t('tabs.shares'), icon: Users },
    { key: 'shared-with-me' as const, label: t('tabs.sharedWithMe'), shortLabel: t('tabs.received'), icon: Share2 },
    { key: 'cloud-exports' as const, label: t('tabs.cloudExports', 'Cloud Shares'), shortLabel: t('tabs.cloudExportsShort', 'Cloud'), icon: Cloud },
  ];

  return (
    <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
      <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all touch-manipulation active:scale-95 ${
              activeTab === tab.key
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.label}</span>
            <span className="sm:hidden">{tab.shortLabel}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesTabBar.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/SharesTabBar.tsx client/src/__tests__/components/shares/SharesTabBar.test.tsx
git commit -m "feat(shares): extract SharesTabBar (F2)"
```

---

### Task 8: `SharesToolbar.tsx`

**Files:**
- Create: `client/src/components/shares/SharesToolbar.tsx`
- Test: `client/src/__tests__/components/shares/SharesToolbar.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  SharesToolbar(props: {
    searchQuery: string;
    onSearch: (v: string) => void;
    statusFilter: 'all' | 'active' | 'expired';
    onStatusFilter: (v: 'all' | 'active' | 'expired') => void;
    showFilters: boolean;
    onToggleFilters: () => void;
    showCreateButton: boolean;
    onCreate: () => void;
  })
  ```

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/SharesToolbar.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesToolbar } from '../../../components/shares/SharesToolbar';

const base = {
  searchQuery: '',
  onSearch: vi.fn(),
  statusFilter: 'all' as const,
  onStatusFilter: vi.fn(),
  showFilters: false,
  onToggleFilters: vi.fn(),
  showCreateButton: true,
  onCreate: vi.fn(),
};

describe('SharesToolbar', () => {
  it('reports search input changes', () => {
    const onSearch = vi.fn();
    render(<SharesToolbar {...base} onSearch={onSearch} />);
    fireEvent.change(screen.getByPlaceholderText('search.placeholder'), { target: { value: 'abc' } });
    expect(onSearch).toHaveBeenCalledWith('abc');
  });

  it('hides the create button when showCreateButton=false', () => {
    render(<SharesToolbar {...base} showCreateButton={false} />);
    expect(screen.queryByText('buttons.shareWithUser')).toBeNull();
  });

  it('renders the status radios only when showFilters=true', () => {
    const { rerender } = render(<SharesToolbar {...base} showFilters={false} />);
    expect(screen.queryByText('search.active')).toBeNull();
    rerender(<SharesToolbar {...base} showFilters={true} />);
    expect(screen.getByText('search.active')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesToolbar.test.tsx`
Expected: FAIL — cannot find module `SharesToolbar`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/SharesToolbar.tsx
import { useTranslation } from 'react-i18next';
import { Search, Filter, Users } from 'lucide-react';

type StatusFilter = 'all' | 'active' | 'expired';

interface SharesToolbarProps {
  searchQuery: string;
  onSearch: (v: string) => void;
  statusFilter: StatusFilter;
  onStatusFilter: (v: StatusFilter) => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  showCreateButton: boolean;
  onCreate: () => void;
}

export function SharesToolbar({
  searchQuery, onSearch, statusFilter, onStatusFilter,
  showFilters, onToggleFilters, showCreateButton, onCreate,
}: SharesToolbarProps) {
  const { t } = useTranslation(['shares', 'common']);

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 sm:w-5 sm:h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={t('search.placeholder')}
            className="w-full pl-10 sm:pl-11 pr-4 py-2.5 sm:py-3 border border-slate-700 bg-slate-900/70 rounded-xl focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-slate-200 placeholder-slate-500 text-sm sm:text-base"
          />
        </div>

        <button
          onClick={onToggleFilters}
          className={`px-4 sm:px-5 py-2.5 sm:py-3 border rounded-xl flex items-center justify-center gap-2 font-medium transition-all touch-manipulation active:scale-95 text-sm sm:text-base ${
            showFilters ? 'bg-blue-500/20 border-blue-500/40 text-blue-400' : 'border-slate-700 text-slate-300 hover:bg-slate-800/50'
          }`}
        >
          <Filter className="w-4 h-4 sm:w-5 sm:h-5" />
          <span>{t('search.filters')}</span>
        </button>

        {showCreateButton && (
          <button
            onClick={onCreate}
            className="btn btn-primary flex items-center justify-center gap-2 touch-manipulation active:scale-95"
          >
            <Users className="w-4 h-4 sm:w-5 sm:h-5" />
            <span className="hidden sm:inline">{t('buttons.shareWithUser')}</span>
            <span className="sm:hidden">{t('buttons.share')}</span>
          </button>
        )}
      </div>

      {showFilters && (
        <div className="flex flex-wrap gap-2 sm:gap-3 p-3 sm:p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
          <span className="text-xs sm:text-sm font-semibold text-slate-300 flex items-center mr-2">
            {t('search.status')}:
          </span>
          {(['all', 'active', 'expired'] as const).map((status) => (
            <label key={status} className="flex items-center cursor-pointer">
              <input
                type="radio"
                value={status}
                checked={statusFilter === status}
                onChange={(e) => onStatusFilter(e.target.value as StatusFilter)}
                className="mr-1.5 sm:mr-2 w-4 h-4 text-sky-500"
              />
              <span className="text-xs sm:text-sm font-medium text-slate-300 capitalize">{t(`search.${status}`)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharesToolbar.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/SharesToolbar.tsx client/src/__tests__/components/shares/SharesToolbar.test.tsx
git commit -m "feat(shares): extract SharesToolbar (F2)"
```

---

### Task 9: `MySharesTable.tsx`

**Files:**
- Create: `client/src/components/shares/MySharesTable.tsx`
- Test: `client/src/__tests__/components/shares/MySharesTable.test.tsx`

**Interfaces:**
- Consumes: `FileShare` (`api/shares`), `SortProps` (`types.ts`), `SortableHeader` (`ui`), `ui/EmptyState`, `PermissionBadges`, `FileNameCell`, `formatDate`.
- Produces:
  ```ts
  MySharesTable(props: SortProps & {
    shares: FileShare[];         // already filtered + sorted
    allCount: number;            // unfiltered count, drives empty-state copy
    onEdit: (share: FileShare) => void;
    onDelete: (shareId: number) => void;
  })
  ```

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/MySharesTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { MySharesTable } from '../../../components/shares/MySharesTable';
import type { FileShare } from '../../../api/shares';

// Full object (all required FileShare fields), then override.
const share = (over: Partial<FileShare> = {}): FileShare => ({
  id: 1, file_id: 10, owner_id: 1, shared_with_user_id: 2,
  can_read: true, can_write: false, can_delete: false, can_share: false,
  expires_at: null, created_at: '2026-01-01T00:00:00Z', last_accessed_at: null,
  is_expired: false, is_accessible: true,
  owner_username: 'alice', shared_with_username: 'bob',
  file_name: 'report.pdf', file_path: '/report.pdf', file_size: 0, is_directory: false,
  ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };

describe('MySharesTable', () => {
  it('shows the "no shares" empty state when there are none at all', () => {
    render(<MySharesTable shares={[]} allCount={0} onEdit={vi.fn()} onDelete={vi.fn()} {...sortProps} />);
    expect(screen.getByText('empty.noShares')).toBeInTheDocument();
  });

  it('shows the "no matching" empty state when filtered to zero', () => {
    render(<MySharesTable shares={[]} allCount={3} onEdit={vi.fn()} onDelete={vi.fn()} {...sortProps} />);
    expect(screen.getByText('empty.noMatchingShares')).toBeInTheDocument();
  });

  it('fires onEdit and onDelete from the row actions (desktop)', () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<MySharesTable shares={[share()]} allCount={1} onEdit={onEdit} onDelete={onDelete} {...sortProps} />);
    // file name appears in both desktop + mobile views
    expect(screen.getAllByText('report.pdf').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByTitle('buttons.edit')[0]);
    fireEvent.click(screen.getAllByTitle('buttons.revoke')[0]);
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
    expect(onDelete).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/MySharesTable.test.tsx`
Expected: FAIL — cannot find module `MySharesTable`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/MySharesTable.tsx
import { useTranslation } from 'react-i18next';
import { Users, Edit, Trash2, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { PermissionBadges } from './PermissionBadges';
import { FileNameCell } from './FileNameCell';
import { formatDate } from './sharesFormat';
import type { FileShare } from '../../api/shares';
import type { SortProps } from './types';

interface MySharesTableProps extends SortProps {
  shares: FileShare[];
  allCount: number;
  onEdit: (share: FileShare) => void;
  onDelete: (shareId: number) => void;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function MySharesTable({ shares, allCount, sortKey, sortDirection, onSort, onEdit, onDelete }: MySharesTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (shares.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title={allCount === 0 ? t('empty.noShares') : t('empty.noMatchingShares')}
        description={allCount === 0 ? t('empty.noSharesDesc') : t('empty.tryAdjusting')}
      />
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.owner')} sortKey="owner_username" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.sharedWith')} sortKey="shared_with_username" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.permissions')}</th>
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {shares.map((share) => (
              <tr key={share.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={share.is_directory} name={share.file_name} size={share.file_size} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.owner_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.shared_with_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <PermissionBadges canRead={share.can_read} canWrite={share.can_write} canDelete={share.can_delete} />
                  </div>
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(share.expires_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <button onClick={() => onEdit(share)} className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20" title={t('buttons.edit')}>
                      <Edit className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                    <button onClick={() => onDelete(share.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20" title={t('buttons.revoke')}>
                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {shares.map((share) => (
          <div key={share.id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <div className="flex items-start justify-between gap-2 mb-3">
              <FileNameCell variant="card" className="min-w-0 flex-1" isDirectory={share.is_directory} name={share.file_name} size={share.file_size} folderLabel={folderLabel} />
              <div className="flex gap-1 flex-shrink-0">
                <button onClick={() => onEdit(share)} className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition touch-manipulation active:scale-95" title={t('buttons.edit')}>
                  <Edit className="w-4 h-4" />
                </button>
                <button onClick={() => onDelete(share.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95" title={t('buttons.revoke')}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{t('table.owner')}: {share.owner_username}</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{share.shared_with_username}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <PermissionBadges size="sm" canRead={share.can_read} canWrite={share.can_write} canDelete={share.can_delete} />
            </div>
            <div className="text-xs text-slate-400 flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {t('table.expires')}: {formatDate(share.expires_at, never)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/MySharesTable.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/MySharesTable.tsx client/src/__tests__/components/shares/MySharesTable.test.tsx
git commit -m "feat(shares): extract MySharesTable (F2)"
```

---

### Task 10: `SharedWithMeTable.tsx`

**Files:**
- Create: `client/src/components/shares/SharedWithMeTable.tsx`
- Test: `client/src/__tests__/components/shares/SharedWithMeTable.test.tsx`

**Interfaces:**
- Consumes: `SharedWithMe` (`api/shares`), `SortProps`, `SortableHeader`, `ui/EmptyState`, `PermissionBadges`, `FileNameCell`, `formatDate`.
- Produces:
  ```ts
  SharedWithMeTable(props: SortProps & { items: SharedWithMe[]; allCount: number })
  ```
  Read-only (no row actions).

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/SharedWithMeTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharedWithMeTable } from '../../../components/shares/SharedWithMeTable';
import type { SharedWithMe } from '../../../api/shares';

// Full object (all required SharedWithMe fields), then override.
const item = (over: Partial<SharedWithMe> = {}): SharedWithMe => ({
  share_id: 7, file_id: 10, file_name: 'photo.jpg', file_path: '/photo.jpg',
  file_size: 0, is_directory: false, owner_username: 'carol', owner_id: 3,
  can_read: true, can_write: false, can_delete: false, can_share: false,
  shared_at: '2026-01-01T00:00:00Z', expires_at: null, is_expired: false, ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };

describe('SharedWithMeTable', () => {
  it('shows the empty state when nothing is shared', () => {
    render(<SharedWithMeTable items={[]} allCount={0} {...sortProps} />);
    expect(screen.getByText('empty.noFilesShared')).toBeInTheDocument();
  });

  it('renders the owner and file name for an item', () => {
    render(<SharedWithMeTable items={[item()]} allCount={1} {...sortProps} />);
    expect(screen.getAllByText('photo.jpg').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/carol/).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharedWithMeTable.test.tsx`
Expected: FAIL — cannot find module `SharedWithMeTable`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/SharedWithMeTable.tsx
import { useTranslation } from 'react-i18next';
import { Share2, Users, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { PermissionBadges } from './PermissionBadges';
import { FileNameCell } from './FileNameCell';
import { formatDate } from './sharesFormat';
import type { SharedWithMe } from '../../api/shares';
import type { SortProps } from './types';

interface SharedWithMeTableProps extends SortProps {
  items: SharedWithMe[];
  allCount: number;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function SharedWithMeTable({ items, allCount, sortKey, sortDirection, onSort }: SharedWithMeTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Share2}
        title={allCount === 0 ? t('empty.noFilesShared') : t('empty.noMatchingFilesShared')}
        description={allCount === 0 ? t('empty.noFilesSharedDesc') : t('empty.tryAdjusting')}
      />
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.owner')} sortKey="owner_username" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.permissions')}</th>
              <SortableHeader label={t('table.shared')} sortKey="shared_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {items.map((item) => (
              <tr key={item.share_id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={item.is_directory} name={item.file_name} size={item.file_size} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{item.owner_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <PermissionBadges canRead={item.can_read} canWrite={item.can_write} canDelete={item.can_delete} />
                  </div>
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(item.shared_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(item.expires_at, never)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {items.map((item) => (
          <div key={item.share_id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <FileNameCell variant="card" className="mb-2" isDirectory={item.is_directory} name={item.file_name} size={item.file_size} folderLabel={folderLabel} />
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{t('table.from')}: {item.owner_username}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <PermissionBadges size="sm" canRead={item.can_read} canWrite={item.can_write} canDelete={item.can_delete} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.shared')}: {formatDate(item.shared_at, never)}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.expires')}: {formatDate(item.expires_at, never)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/SharedWithMeTable.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/SharedWithMeTable.tsx client/src/__tests__/components/shares/SharedWithMeTable.test.tsx
git commit -m "feat(shares): extract SharedWithMeTable (F2)"
```

---

### Task 11: `CloudExportsTable.tsx`

**Files:**
- Create: `client/src/components/shares/CloudExportsTable.tsx`
- Test: `client/src/__tests__/components/shares/CloudExportsTable.test.tsx`

**Interfaces:**
- Consumes: `CloudExportJob` (`api/cloud-export`), `SortProps`, `SortableHeader`, `ui/EmptyState`, `CloudStatusBadge`, `FileNameCell`, `formatDate`, `getProviderLabel`.
- Produces:
  ```ts
  CloudExportsTable(props: SortProps & {
    jobs: CloudExportJob[];
    onCopyLink: (link: string) => void;
    onRevoke: (jobId: number) => void;
    onRetry: (jobId: number) => void;
  })
  ```
  Action visibility: Copy only when `share_link`; Revoke only when `status === 'ready'`; Retry only when `status === 'failed'`. Empty state has no `allCount` distinction (matches original — single message).

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/shares/CloudExportsTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { CloudExportsTable } from '../../../components/shares/CloudExportsTable';
import type { CloudExportJob } from '../../../api/cloud-export';

// Full object (all required CloudExportJob fields), then override.
const job = (over: Partial<CloudExportJob> = {}): CloudExportJob => ({
  id: 1, user_id: 1, connection_id: 1, source_path: '/f.zip', file_name: 'f.zip',
  is_directory: false, file_size_bytes: 0, cloud_folder: '/', cloud_path: null,
  share_link: 'https://example.com/x', link_type: 'view', status: 'ready',
  progress_bytes: 0, error_message: null, created_at: '2026-01-01T00:00:00Z',
  completed_at: null, expires_at: null, ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };
const handlers = { onCopyLink: vi.fn(), onRevoke: vi.fn(), onRetry: vi.fn() };

describe('CloudExportsTable', () => {
  it('shows the empty state when there are no jobs', () => {
    render(<CloudExportsTable jobs={[]} {...sortProps} {...handlers} />);
    expect(screen.getByText('shares:cloudExport.noExports')).toBeInTheDocument();
  });

  it('shows Revoke (ready) but not Retry, and fires onRevoke', () => {
    const onRevoke = vi.fn();
    render(<CloudExportsTable jobs={[job({ status: 'ready' })]} {...sortProps} {...handlers} onRevoke={onRevoke} />);
    expect(screen.queryAllByTitle('shares:cloudExport.retry')).toHaveLength(0);
    fireEvent.click(screen.getAllByTitle('shares:cloudExport.revoke')[0]);
    expect(onRevoke).toHaveBeenCalledWith(1);
  });

  it('shows Retry (failed) but not Revoke, and fires onRetry', () => {
    const onRetry = vi.fn();
    render(<CloudExportsTable jobs={[job({ status: 'failed' })]} {...sortProps} {...handlers} onRetry={onRetry} />);
    expect(screen.queryAllByTitle('shares:cloudExport.revoke')).toHaveLength(0);
    fireEvent.click(screen.getAllByTitle('shares:cloudExport.retry')[0]);
    expect(onRetry).toHaveBeenCalledWith(1);
  });

  it('hides copy affordances when there is no share_link', () => {
    render(<CloudExportsTable jobs={[job({ share_link: null, status: 'pending' })]} {...sortProps} {...handlers} />);
    expect(screen.queryAllByTitle('shares:cloudExport.copyLink')).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/shares/CloudExportsTable.test.tsx`
Expected: FAIL — cannot find module `CloudExportsTable`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/shares/CloudExportsTable.tsx
import { useTranslation } from 'react-i18next';
import { Cloud, Copy, Trash2, RefreshCw, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { CloudStatusBadge } from './CloudStatusBadge';
import { FileNameCell } from './FileNameCell';
import { formatDate, getProviderLabel } from './sharesFormat';
import type { CloudExportJob } from '../../api/cloud-export';
import type { SortProps } from './types';

interface CloudExportsTableProps extends SortProps {
  jobs: CloudExportJob[];
  onCopyLink: (link: string) => void;
  onRevoke: (jobId: number) => void;
  onRetry: (jobId: number) => void;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function CloudExportsTable({ jobs, sortKey, sortDirection, onSort, onCopyLink, onRevoke, onRetry }: CloudExportsTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (jobs.length === 0) {
    return (
      <EmptyState
        icon={Cloud}
        title={t('shares:cloudExport.noExports', 'No cloud shares')}
        description={t('shares:cloudExport.noExportsDesc', 'Share files to cloud storage from the file manager.')}
      />
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label={t('shares:cloudExport.provider', 'Provider')} sortKey="provider" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('shares:cloudExport.link', 'Link')}</th>
              <SortableHeader label={t('search.status', 'Status')} sortKey="status" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('shares:cloudExport.created', 'Created')} sortKey="created_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {jobs.map((job) => (
              <tr key={job.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4"><span className="text-slate-300 font-medium">{getProviderLabel(job)}</span></td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={job.is_directory} name={job.file_name} size={job.file_size_bytes} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  {job.share_link ? (
                    <button onClick={() => onCopyLink(job.share_link!)} className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-sm" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                      <Copy className="w-3.5 h-3.5" />
                      <span className="truncate max-w-[160px]">{t('shares:cloudExport.copyLink', 'Copy link')}</span>
                    </button>
                  ) : (
                    <span className="text-slate-500 text-sm">--</span>
                  )}
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4"><CloudStatusBadge job={job} /></td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(job.created_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(job.expires_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    {job.share_link && (
                      <button onClick={() => onCopyLink(job.share_link!)} className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition hover:border-blue-500/50 hover:bg-blue-500/20" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                        <Copy className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                    {job.status === 'ready' && (
                      <button onClick={() => onRevoke(job.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20" title={t('shares:cloudExport.revoke', 'Revoke')}>
                        <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                    {job.status === 'failed' && (
                      <button onClick={() => onRetry(job.id)} className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20" title={t('shares:cloudExport.retry', 'Retry')}>
                        <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {jobs.map((job) => (
          <div key={job.id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <div className="flex items-start justify-between gap-2 mb-3">
              <FileNameCell variant="card" className="min-w-0 flex-1" isDirectory={job.is_directory} name={job.file_name} size={job.file_size_bytes} folderLabel={folderLabel} />
              <div className="flex gap-1 flex-shrink-0">
                {job.share_link && (
                  <button onClick={() => onCopyLink(job.share_link!)} className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                    <Copy className="w-4 h-4" />
                  </button>
                )}
                {job.status === 'ready' && (
                  <button onClick={() => onRevoke(job.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.revoke', 'Revoke')}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
                {job.status === 'failed' && (
                  <button onClick={() => onRetry(job.id)} className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.retry', 'Retry')}>
                    <RefreshCw className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Cloud className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{getProviderLabel(job)}</span>
            </div>
            <div className="flex items-center gap-2 mb-2"><CloudStatusBadge job={job} /></div>
            {job.share_link && (
              <button onClick={() => onCopyLink(job.share_link!)} className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-xs mb-2">
                <Copy className="w-3 h-3" />
                {t('shares:cloudExport.copyLink', 'Copy link')}
              </button>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('shares:cloudExport.created', 'Created')}: {formatDate(job.created_at, never)}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.expires')}: {formatDate(job.expires_at, never)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/shares/CloudExportsTable.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/shares/CloudExportsTable.tsx client/src/__tests__/components/shares/CloudExportsTable.test.tsx
git commit -m "feat(shares): extract CloudExportsTable (F2)"
```

---

### Task 12: Barrel + rewire `SharesPage.tsx` + docs + full verify

**Files:**
- Create: `client/src/components/shares/index.ts`
- Modify: `client/src/pages/SharesPage.tsx` (full rewrite to orchestrator, target < 250 lines)
- Modify: `client/src/pages/CLAUDE.md` (SharesPage row note)
- Modify: `client/src/components/CLAUDE.md` (add `shares/` to the feature-subdirectory table)

**Interfaces:**
- Consumes: all Task 1–11 exports.
- Produces: nothing new (integration task).

- [ ] **Step 1: Create the barrel**

```ts
// client/src/components/shares/index.ts
export { PermissionBadges } from './PermissionBadges';
export { FileNameCell } from './FileNameCell';
export { CloudStatusBadge } from './CloudStatusBadge';
export { SharesStatCards } from './SharesStatCards';
export { SharesTabBar } from './SharesTabBar';
export { SharesToolbar } from './SharesToolbar';
export { MySharesTable } from './MySharesTable';
export { SharedWithMeTable } from './SharedWithMeTable';
export { CloudExportsTable } from './CloudExportsTable';
export { formatDate, formatFileSize, getProviderLabel } from './sharesFormat';
export type { SharesTab, SortProps } from './types';
```

- [ ] **Step 2: Rewrite `SharesPage.tsx`**

Replace the ENTIRE file with:

```tsx
// client/src/pages/SharesPage.tsx
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Loader2 } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteFileShare, getShareableUsers, type FileShare } from '../api/shares';
import { useFileShares } from '../hooks/useFileShares';
import { useCloudExports } from '../hooks/useCloudExports';
import { useSortableTable } from '../hooks/useSortableTable';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { queryKeys } from '../lib/queryKeys';
import CreateFileShareModal from '../components/CreateFileShareModal';
import EditFileShareModal from '../components/EditFileShareModal';
import {
  SharesStatCards,
  SharesTabBar,
  SharesToolbar,
  MySharesTable,
  SharedWithMeTable,
  CloudExportsTable,
  getProviderLabel,
  type SharesTab,
} from '../components/shares';

type StatusFilter = 'all' | 'active' | 'expired';

export default function SharesPage() {
  const { t } = useTranslation(['shares', 'common']);
  const { confirm, dialog } = useConfirmDialog();
  const queryClient = useQueryClient();

  const [users, setUsers] = useState<Array<{ id: number; username: string; role: string }>>([]);
  const [activeTab, setActiveTab] = useState<SharesTab>('shares');
  const [showCreateShareModal, setShowCreateShareModal] = useState(false);
  const [editingShare, setEditingShare] = useState<FileShare | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showFilters, setShowFilters] = useState(false);

  const { fileShares, sharedWithMe, statistics, loading: sharesLoading } = useFileShares();
  const { cloudExports, cloudStats, loading: cloudLoading, revoke, retry } = useCloudExports();
  const loading = sharesLoading || cloudLoading;

  useEffect(() => {
    getShareableUsers()
      .then((data) => setUsers(Array.isArray(data) ? data.map((u) => ({ id: u.id, username: u.username, role: '' })) : []))
      .catch(() => setUsers([]));
  }, []);

  const deleteShareMutation = useMutation({
    mutationFn: (shareId: number) => deleteFileShare(shareId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() }); },
    onError: () => { toast.error(t('shares:toast.revokeFailed')); },
  });

  const handleDeleteFileShare = async (shareId: number) => {
    const ok = await confirm(t('confirm.revokeShare'), { title: t('confirm.revokeShare'), variant: 'danger', confirmLabel: t('common:actions.revoke', 'Revoke') });
    if (!ok) return;
    deleteShareMutation.mutate(shareId);
  };

  const handleCopyLink = (link: string) => {
    navigator.clipboard.writeText(link);
    toast.success(t('shares:cloudExport.linkCopied', 'Link copied'));
  };

  const handleRevokeExport = async (jobId: number) => {
    const ok = await confirm(t('shares:cloudExport.revokeConfirm', 'Revoke this cloud share?'), {
      title: t('shares:cloudExport.revoke', 'Revoke'), variant: 'danger', confirmLabel: t('shares:cloudExport.revoke', 'Revoke'),
    });
    if (!ok) return;
    await revoke(jobId);
  };

  const matchesFilters = (isExpired: boolean, ...fields: Array<string | null | undefined>) => {
    if (statusFilter === 'active' && isExpired) return false;
    if (statusFilter === 'expired' && !isExpired) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return fields.some((f) => f?.toLowerCase().includes(q));
    }
    return true;
  };

  const filteredFileShares = Array.isArray(fileShares)
    ? fileShares.filter((s) => matchesFilters(s.is_expired, s.file_name, s.shared_with_username))
    : [];
  const filteredSharedWithMe = Array.isArray(sharedWithMe)
    ? sharedWithMe.filter((i) => matchesFilters(i.is_expired, i.file_name, i.owner_username))
    : [];

  const shares = useSortableTable(filteredFileShares);
  const shared = useSortableTable(filteredSharedWithMe);
  const cloud = useSortableTable(cloudExports, { getValueForSort: { provider: (job) => getProviderLabel(job) } });

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('description')}</p>
        </div>
      </div>

      <SharesStatCards activeTab={activeTab} statistics={statistics} cloudStats={cloudStats} />
      <SharesTabBar activeTab={activeTab} onChange={setActiveTab} />
      <SharesToolbar
        searchQuery={searchQuery}
        onSearch={setSearchQuery}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters((v) => !v)}
        showCreateButton={activeTab === 'shares'}
        onCreate={() => setShowCreateShareModal(true)}
      />

      {/* Content */}
      <div className="card border-slate-800/60 bg-slate-900/55 overflow-hidden">
        <div className="p-4 sm:p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 sm:py-16">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-4" />
              <p className="text-slate-400 font-medium text-sm sm:text-base">{t('loading')}</p>
            </div>
          ) : (
            <>
              {activeTab === 'shares' && (
                <MySharesTable
                  shares={shares.sortedData}
                  allCount={fileShares.length}
                  sortKey={shares.sortKey}
                  sortDirection={shares.sortDirection}
                  onSort={shares.toggleSort}
                  onEdit={setEditingShare}
                  onDelete={handleDeleteFileShare}
                />
              )}
              {activeTab === 'shared-with-me' && (
                <SharedWithMeTable
                  items={shared.sortedData}
                  allCount={sharedWithMe.length}
                  sortKey={shared.sortKey}
                  sortDirection={shared.sortDirection}
                  onSort={shared.toggleSort}
                />
              )}
              {activeTab === 'cloud-exports' && (
                <CloudExportsTable
                  jobs={cloud.sortedData}
                  sortKey={cloud.sortKey}
                  sortDirection={cloud.sortDirection}
                  onSort={cloud.toggleSort}
                  onCopyLink={handleCopyLink}
                  onRevoke={handleRevokeExport}
                  onRetry={retry}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showCreateShareModal && (
        <CreateFileShareModal users={users} onClose={() => setShowCreateShareModal(false)} onSuccess={() => setShowCreateShareModal(false)} />
      )}
      {editingShare && (
        <EditFileShareModal fileShare={editingShare} onClose={() => setEditingShare(null)} onSuccess={() => setEditingShare(null)} />
      )}
      {dialog}
    </div>
  );
}
```

- [ ] **Step 3: Verify the page shrank**

Run: `cd client && node -e "console.log(require('fs').readFileSync('src/pages/SharesPage.tsx','utf8').split(/\r?\n/).length)"`
Expected: a number **< 250**.

- [ ] **Step 4: Type-check + lint + full unit suite**

Run: `cd client && npx eslint . && npm run build && npx vitest run`
Expected: eslint 0 errors; `npm run build` (tsc -b + vite) success; vitest all green (new shares tests + existing suite).

> If `eslint` flags an unused import in the rewritten page (e.g. a lucide icon no longer used), remove it. The page should import ONLY: `Loader2` from lucide, and the symbols shown above.

- [ ] **Step 5: Update docs**

In `client/src/pages/CLAUDE.md`, change the `SharesPage.tsx` row description to note the decomposition, e.g.:
`| `SharesPage.tsx` | `/shares` | Yes | File share management — composes `components/shares/*` (tables/toolbar/stat-cards, extracted F2) |`

In `client/src/components/CLAUDE.md`, add a row to the Feature Subdirectories table (keep alphabetical-ish placement near `settings/`):
`| `shares/` | Share management — `SharesPage` composes `SharesStatCards`, `SharesTabBar`, `SharesToolbar`, `MySharesTable`, `SharedWithMeTable`, `CloudExportsTable` (+ `PermissionBadges`/`FileNameCell`/`CloudStatusBadge` primitives), extracted F2/#301-style |`

- [ ] **Step 6: Commit**

```bash
git add client/src/components/shares/index.ts client/src/pages/SharesPage.tsx client/src/pages/CLAUDE.md client/src/components/CLAUDE.md
git commit -m "refactor(shares): compose SharesPage from extracted shares/* components, page under 250 (F2)"
```

---

## Manual Verification (after Task 12)

Start dev (`python start_dev.py`), log in, open `/shares`:

- [ ] **My Shares tab:** list renders (desktop table + mobile card at <1024px); search filters by file/user; status filter all/active/expired; Edit opens `EditFileShareModal`; Revoke prompts confirm → removes; sort headers toggle.
- [ ] **Shared with me tab:** list renders; empty state when none; filters work.
- [ ] **Cloud Shares tab:** stat cards switch to cloud variant; Copy link (only with link), Revoke (only `ready`, prompts), Retry (only `failed`); status badge incl. upload %.
- [ ] Empty states render via `ui/EmptyState` (gray circle) — the accepted visual normalization.

---

## Self-Review Notes (author)

- **Spec coverage:** every design component (10 shares/* files + `useCloudExports` + tests + docs) maps to Tasks 1–12. ✓
- **Type consistency:** `SortProps` defined in Task 1, consumed identically in Tasks 9–11. `SharesTab` defined Task 1, used in Tasks 6/7 + page. `useCloudExports` return shape (Task 5) matches page usage (Task 12: `revoke`, `retry`, `cloudExports`, `cloudStats`, `loading`). ✓
- **Cloud handler split:** `revoke`/`retry` in the hook do the API+reload+toast; the page adds the confirm for revoke and passes `retry` straight through — matches original behavior. ✓
- **Field names verified against source usage:** `FileShare` (file_name/is_directory/file_size/owner_username/shared_with_username/can_*/expires_at/is_expired), `SharedWithMe` (share_id/shared_at/…), `CloudExportJob` (file_size_bytes/progress_bytes/share_link/status/created_at/expires_at). If any type field differs at implementation time, trust the actual `api/*.ts` type and adjust the prop wiring (not the type).
