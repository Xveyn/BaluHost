# Sortable Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-side sortable column headers with a 3-stage cycle (default -> asc -> desc -> default) to File Manager, Shares, User Management, and Pi-hole Local DNS tables.

**Architecture:** Create a reusable `useSortableTable` hook for client-side sorting and a `SortableHeader` component for clickable column headers with directional icons. Integrate into 4 target areas and retrofit the 3-stage cycle into AdminDataTable and UserManagement.

**Tech Stack:** React hooks, TypeScript, lucide-react icons (ArrowUp, ArrowDown, ArrowUpDown), Tailwind CSS

---

### Task 1: Create `useSortableTable` Hook

**Files:**
- Create: `client/src/hooks/useSortableTable.ts`

- [ ] **Step 1: Create the hook file**

```typescript
// client/src/hooks/useSortableTable.ts
import { useState, useMemo } from 'react';

export type SortDirection = 'asc' | 'desc' | null;

interface SortState {
  key: string | null;
  direction: SortDirection;
}

interface UseSortableTableOptions<T> {
  defaultSort?: { key: string; direction: 'asc' | 'desc' };
  getValueForSort?: Record<string, (item: T) => string | number | boolean | Date | null | undefined>;
}

function detectAndCompare(a: unknown, b: unknown): number {
  // nulls/undefined always last
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  // booleans: false < true
  if (typeof a === 'boolean' && typeof b === 'boolean') {
    return a === b ? 0 : a ? 1 : -1;
  }

  // numbers
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }

  // Date objects
  if (a instanceof Date && b instanceof Date) {
    return a.getTime() - b.getTime();
  }

  // strings — try ISO date parse, then numeric parse, then localeCompare
  const strA = String(a);
  const strB = String(b);

  // ISO date detection (starts with 4-digit year)
  if (/^\d{4}-\d{2}/.test(strA) && /^\d{4}-\d{2}/.test(strB)) {
    const da = new Date(strA).getTime();
    const db = new Date(strB).getTime();
    if (!isNaN(da) && !isNaN(db)) return da - db;
  }

  // numeric strings
  const numA = Number(strA);
  const numB = Number(strB);
  if (!isNaN(numA) && !isNaN(numB) && strA !== '' && strB !== '') {
    return numA - numB;
  }

  // fallback: case-insensitive string comparison
  return strA.localeCompare(strB, undefined, { sensitivity: 'base' });
}

export function useSortableTable<T extends Record<string, unknown>>(
  data: T[],
  options?: UseSortableTableOptions<T>,
) {
  const [sort, setSort] = useState<SortState>(() => ({
    key: options?.defaultSort?.key ?? null,
    direction: options?.defaultSort?.direction ?? null,
  }));

  const toggleSort = (key: string) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, direction: 'asc' };
      if (prev.direction === 'asc') return { key, direction: 'desc' };
      if (prev.direction === 'desc') return { key: null, direction: null };
      return { key, direction: 'asc' };
    });
  };

  const resetSort = () => setSort({ key: null, direction: null });

  const sortedData = useMemo(() => {
    if (!sort.key || !sort.direction) return data;

    const key = sort.key;
    const dir = sort.direction === 'asc' ? 1 : -1;
    const customGetter = options?.getValueForSort?.[key];

    return [...data].sort((a, b) => {
      const valA = customGetter ? customGetter(a) : a[key];
      const valB = customGetter ? customGetter(b) : b[key];
      return dir * detectAndCompare(valA, valB);
    });
  }, [data, sort.key, sort.direction, options?.getValueForSort]);

  return {
    sortedData,
    sortKey: sort.key,
    sortDirection: sort.direction,
    toggleSort,
    resetSort,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/hooks/useSortableTable.ts
git commit -m "feat: add useSortableTable hook with 3-stage sort cycle"
```

---

### Task 2: Create `SortableHeader` Component

**Files:**
- Create: `client/src/components/ui/SortableHeader.tsx`

- [ ] **Step 1: Create the component file**

```tsx
// client/src/components/ui/SortableHeader.tsx
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import type { SortDirection } from '../../hooks/useSortableTable';

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  activeSortKey: string | null;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
  className?: string;
}

export function SortableHeader({
  label,
  sortKey,
  activeSortKey,
  sortDirection,
  onSort,
  className = '',
}: SortableHeaderProps) {
  const isActive = activeSortKey === sortKey;

  return (
    <th
      className={`cursor-pointer select-none group/sh transition-colors hover:text-slate-200 ${className}`}
      onClick={() => onSort(sortKey)}
    >
      <div className="flex items-center gap-1.5">
        <span>{label}</span>
        <span className="flex-shrink-0">
          {isActive && sortDirection === 'asc' ? (
            <ArrowUp className="w-3.5 h-3.5 text-blue-400" />
          ) : isActive && sortDirection === 'desc' ? (
            <ArrowDown className="w-3.5 h-3.5 text-blue-400" />
          ) : (
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-600 group-hover/sh:text-slate-400 transition-colors" />
          )}
        </span>
      </div>
    </th>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/ui/SortableHeader.tsx
git commit -m "feat: add SortableHeader component with sort icons"
```

---

### Task 3: Integrate Sorting into FileListView

**Files:**
- Modify: `client/src/components/file-manager/FileListView.tsx:1-3` (imports)
- Modify: `client/src/components/file-manager/FileListView.tsx:91-114` (component body, add hook)
- Modify: `client/src/components/file-manager/FileListView.tsx:136-147` (table headers)
- Modify: `client/src/components/file-manager/FileListView.tsx:156` (iterate sortedData instead of files)

- [ ] **Step 1: Add imports at top of FileListView.tsx**

Add after the existing imports (after line 18):

```typescript
import { useSortableTable } from '../../hooks/useSortableTable';
import { SortableHeader } from '../ui/SortableHeader';
```

- [ ] **Step 2: Add the hook inside the component**

Inside `FileListView` function body, before the `return` statement (after line 114), add:

```typescript
  const { sortedData, sortKey, sortDirection, toggleSort } = useSortableTable(files, {
    getValueForSort: {
      owner: (file) => renderOwnerName(file, userCache),
    },
  });
```

- [ ] **Step 3: Replace table headers with SortableHeader**

Replace the `<thead>` block (lines 138-146) with:

```tsx
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label="Name" sortKey="name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Type</th>
              <SortableHeader label="Size" sortKey="size" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <SortableHeader label="Modified" sortKey="modifiedAt" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <SortableHeader label="Owner" sortKey="owner" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
```

- [ ] **Step 4: Use sortedData instead of files for desktop table rows**

Change the `files.map` on line 156 to `sortedData.map`:

```tsx
              sortedData.map((file) => (
```

Also change the empty check on line 149:

```tsx
            {sortedData.length === 0 ? (
```

- [ ] **Step 5: Use sortedData for mobile card view too**

Find the mobile view section (after the desktop table, around line ~250+) where `files.map` is used for the mobile card layout. Change it to `sortedData.map` as well. The mobile cards don't have headers to click but should show data in the same sorted order.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/file-manager/FileListView.tsx
git commit -m "feat: add sortable columns to FileListView (Name, Size, Modified, Owner)"
```

---

### Task 4: Integrate Sorting into SharesPage — My Shares Tab

**Files:**
- Modify: `client/src/pages/SharesPage.tsx`

- [ ] **Step 1: Add imports**

Add after existing imports (around line 27):

```typescript
import { useSortableTable } from '../hooks/useSortableTable';
import { SortableHeader } from '../components/ui/SortableHeader';
```

- [ ] **Step 2: Add hook for My Shares inside the component**

Inside `SharesPage` component, after the `filteredFileShares` declaration (after line 188), add:

```typescript
  const {
    sortedData: sortedFileShares,
    sortKey: sharesSortKey,
    sortDirection: sharesSortDir,
    toggleSort: toggleSharesSort,
  } = useSortableTable(filteredFileShares);
```

- [ ] **Step 3: Replace My Shares table headers**

Replace the `<thead>` in the My Shares desktop table (lines 373-381) with:

```tsx
                        <thead className="bg-slate-800/30 border-b border-slate-700/50">
                          <tr>
                            <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sharesSortKey} sortDirection={sharesSortDir} onSort={toggleSharesSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                            <SortableHeader label={t('table.owner')} sortKey="owner_username" activeSortKey={sharesSortKey} sortDirection={sharesSortDir} onSort={toggleSharesSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                            <SortableHeader label={t('table.sharedWith')} sortKey="shared_with_username" activeSortKey={sharesSortKey} sortDirection={sharesSortDir} onSort={toggleSharesSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                            <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.permissions')}</th>
                            <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sharesSortKey} sortDirection={sharesSortDir} onSort={toggleSharesSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                            <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.actions')}</th>
                          </tr>
                        </thead>
```

- [ ] **Step 4: Use sortedFileShares instead of filteredFileShares for rows**

Replace `filteredFileShares.map` in the desktop table body (line 384) and mobile card view (line 449) with `sortedFileShares.map`.

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/SharesPage.tsx
git commit -m "feat: add sortable columns to SharesPage My Shares tab"
```

---

### Task 5: Integrate Sorting into SharesPage — Shared With Me Tab

**Files:**
- Modify: `client/src/pages/SharesPage.tsx`

- [ ] **Step 1: Add hook for Shared With Me**

After the My Shares hook added in Task 4, add:

```typescript
  const {
    sortedData: sortedSharedWithMe,
    sortKey: sharedSortKey,
    sortDirection: sharedSortDir,
    toggleSort: toggleSharedSort,
  } = useSortableTable(filteredSharedWithMe);
```

- [ ] **Step 2: Replace Shared With Me table headers**

Replace the `<thead>` in the Shared With Me desktop table (lines 542-549) with:

```tsx
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sharedSortKey} sortDirection={sharedSortDir} onSort={toggleSharedSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <SortableHeader label={t('table.owner')} sortKey="owner_username" activeSortKey={sharedSortKey} sortDirection={sharedSortDir} onSort={toggleSharedSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.permissions')}</th>
                              <SortableHeader label={t('table.shared')} sortKey="shared_at" activeSortKey={sharedSortKey} sortDirection={sharedSortDir} onSort={toggleSharedSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sharedSortKey} sortDirection={sharedSortDir} onSort={toggleSharedSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                            </tr>
                          </thead>
```

- [ ] **Step 3: Use sortedSharedWithMe for rows**

Replace `filteredSharedWithMe.map` in the desktop tbody (line 552) and mobile card view (line 601) with `sortedSharedWithMe.map`.

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/SharesPage.tsx
git commit -m "feat: add sortable columns to SharesPage Shared With Me tab"
```

---

### Task 6: Integrate Sorting into SharesPage — Cloud Exports Tab

**Files:**
- Modify: `client/src/pages/SharesPage.tsx`

- [ ] **Step 1: Add hook for Cloud Exports**

After the Shared With Me hook, add:

```typescript
  const {
    sortedData: sortedCloudExports,
    sortKey: cloudSortKey,
    sortDirection: cloudSortDir,
    toggleSort: toggleCloudSort,
  } = useSortableTable(cloudExports, {
    getValueForSort: {
      provider: (job) => {
        if (job.share_link?.includes('drive.google')) return 'Google Drive';
        if (job.share_link?.includes('1drv.ms') || job.share_link?.includes('sharepoint')) return 'OneDrive';
        return 'Cloud';
      },
    },
  });
```

- [ ] **Step 2: Replace Cloud Exports table headers**

Replace the `<thead>` in the Cloud Exports desktop table (lines 675-684) with:

```tsx
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <SortableHeader label={t('shares:cloudExport.provider', 'Provider')} sortKey="provider" activeSortKey={cloudSortKey} sortDirection={cloudSortDir} onSort={toggleCloudSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={cloudSortKey} sortDirection={cloudSortDir} onSort={toggleCloudSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shares:cloudExport.link', 'Link')}</th>
                              <SortableHeader label={t('search.status', 'Status')} sortKey="status" activeSortKey={cloudSortKey} sortDirection={cloudSortDir} onSort={toggleCloudSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <SortableHeader label={t('shares:cloudExport.created', 'Created')} sortKey="created_at" activeSortKey={cloudSortKey} sortDirection={cloudSortDir} onSort={toggleCloudSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={cloudSortKey} sortDirection={cloudSortDir} onSort={toggleCloudSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.actions')}</th>
                            </tr>
                          </thead>
```

- [ ] **Step 3: Use sortedCloudExports for rows**

Replace `cloudExports.map` in the desktop tbody (line 687) and mobile card view with `sortedCloudExports.map`.

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/SharesPage.tsx
git commit -m "feat: add sortable columns to SharesPage Cloud Exports tab"
```

---

### Task 7: Upgrade UserTable to 3-Stage Cycle + All Columns Sortable

**Files:**
- Modify: `client/src/hooks/useUserManagement.ts:46-47` (sortBy initial state)
- Modify: `client/src/hooks/useUserManagement.ts:97-106` (handleSort)
- Modify: `client/src/components/user-management/UserTable.tsx:1-2` (imports)
- Modify: `client/src/components/user-management/UserTable.tsx:37-66` (table headers)

- [ ] **Step 1: Update useUserManagement — change sortBy default to null and update handleSort**

In `client/src/hooks/useUserManagement.ts`, change line 46:

```typescript
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | null>(null);
```

Replace `handleSort` (lines 97-106) with a 3-stage cycle:

```typescript
  const handleSort = useCallback((field: string) => {
    if (sortBy !== field) {
      setSortBy(field);
      setSortOrder('asc');
    } else if (sortOrder === 'asc') {
      setSortOrder('desc');
    } else {
      setSortBy(null);
      setSortOrder(null);
    }
  }, [sortBy, sortOrder]);
```

And update `loadUsers` to only pass sort params when sortBy is not null (line 68-74):

```typescript
      const data: UsersResponse = await listUsers({
        search: debouncedSearch || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter || undefined,
        sort_by: sortBy || undefined,
        sort_order: sortBy && sortOrder ? sortOrder : undefined,
      });
```

Update the useEffect dependency (line 90) — `sortOrder` can be null now, so the dependency is fine as-is.

- [ ] **Step 2: Update UserTable component**

Replace imports (line 2) in `UserTable.tsx`:

```typescript
import { Trash2, Edit, CheckCircle, XCircle } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import type { SortDirection } from '../../hooks/useSortableTable';
```

Update the `UserTableProps` interface (lines 8-9):

```typescript
  sortBy: string | null;
  sortOrder: SortDirection;
```

Remove the unused `_sortOrder` rename in the destructuring (line 29):

```typescript
  sortOrder,
```

Replace the header `<tr>` content (lines 37-66) with:

```tsx
            <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
              <th className="px-6 py-4">
                <input
                  type="checkbox"
                  checked={selectedUsers.size === users.length && users.length > 0}
                  onChange={onToggleAll}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                />
              </th>
              <SortableHeader label={t('users.fields.username')} sortKey="username" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.email')} sortKey="email" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.role')} sortKey="role" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.status')} sortKey="is_active" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.created')} sortKey="created_at" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <th className="px-6 py-4">{t('users.fields.actions')}</th>
            </tr>
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useUserManagement.ts client/src/components/user-management/UserTable.tsx
git commit -m "feat: upgrade UserTable to 3-stage sort cycle, all columns sortable"
```

---

### Task 8: Integrate Sorting into PiholeLocalDns

**Files:**
- Modify: `client/src/components/pihole/PiholeLocalDns.tsx:1-8` (imports)
- Modify: `client/src/components/pihole/PiholeLocalDns.tsx:98-104` (table header)
- Modify: `client/src/components/pihole/PiholeLocalDns.tsx:107` (use sortedData)

- [ ] **Step 1: Add imports**

Add after the existing imports (after line 8):

```typescript
import { useSortableTable } from '../../hooks/useSortableTable';
import { SortableHeader } from '../ui/SortableHeader';
```

- [ ] **Step 2: Add the hook inside the component**

Inside the `PiholeLocalDns` function, after the state declarations (after line 21), add:

```typescript
  const { sortedData: sortedRecords, sortKey, sortDirection, toggleSort } = useSortableTable(records);
```

- [ ] **Step 3: Replace table headers**

Replace lines 99-104 with:

```tsx
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs uppercase text-slate-500">
                <SortableHeader label="Domain" sortKey="domain" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="pb-2 pr-4" />
                <SortableHeader label="IP Address" sortKey="ip" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="pb-2 pr-4" />
                <th className="pb-2 w-10" />
              </tr>
            </thead>
```

- [ ] **Step 4: Use sortedRecords for rows**

Change `records.map` on line 107 to `sortedRecords.map`:

```tsx
              {sortedRecords.map((r, i) => (
```

- [ ] **Step 5: Commit**

```bash
git add client/src/components/pihole/PiholeLocalDns.tsx
git commit -m "feat: add sortable columns to PiholeLocalDns (Domain, IP)"
```

---

### Task 9: Retrofit AdminDataTable 3-Stage Cycle

**Files:**
- Modify: `client/src/components/AdminDataTable.tsx:93-100` (handleHeaderClick)
- Modify: `client/src/components/AdminDataTable.tsx:20-23` (Props interface)
- Modify: `client/src/pages/AdminDatabase.tsx:34-35` (state types)
- Modify: `client/src/pages/AdminDatabase.tsx:137-141` (handleSortChange)

- [ ] **Step 1: Update AdminDataTable Props and handleHeaderClick**

In `AdminDataTable.tsx`, update the `onSortChange` prop type (line 22):

```typescript
  onSortChange?: (column: string | null, order: 'asc' | 'desc' | null) => void
```

Replace `handleHeaderClick` (lines 93-100):

```typescript
  const handleHeaderClick = (colName: string) => {
    if (!onSortChange) return
    if (sortBy === colName) {
      if (sortOrder === 'asc') {
        onSortChange(colName, 'desc')
      } else {
        // desc -> reset to default
        onSortChange(null, null)
      }
    } else {
      onSortChange(colName, 'asc')
    }
  }
```

- [ ] **Step 2: Update AdminDatabase state and handler**

In `AdminDatabase.tsx`, update state types (lines 34-35):

```typescript
  const [sortBy, setSortBy] = useState<string | null>(null)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | null>(null)
```

Update `handleSortChange` (lines 137-141):

```typescript
  const handleSortChange = useCallback((column: string | null, order: 'asc' | 'desc' | null) => {
    setSortBy(column)
    setSortOrder(order)
    setPage(1)
  }, [])
```

Update the API call params (lines 106-107) to handle null:

```typescript
    const sortByParam = sortBy || undefined
    const sortOrderParam = sortBy && sortOrder ? sortOrder : undefined
```

These lines already exist and handle null correctly since `sortBy || undefined` converts null to undefined.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/AdminDataTable.tsx client/src/pages/AdminDatabase.tsx
git commit -m "feat: upgrade AdminDataTable to 3-stage sort cycle (asc -> desc -> default)"
```

---

### Task 10: Verify All Tables Build and Work

**Files:** None (verification only)

- [ ] **Step 1: Run TypeScript compilation check**

```bash
cd client && npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 2: Run dev server and manually verify**

```bash
cd .. && python start_dev.py
```

Open `http://localhost:5173` and test each table:
1. **File Manager** — Click Name, Size, Modified, Owner headers. Verify 3-stage cycle.
2. **Shares** — Test all 3 tabs (My Shares, Shared With Me, Cloud Exports).
3. **User Management** — Click Username, Email, Role, Status, Created headers.
4. **Pi-hole > Local DNS** — Click Domain and IP headers.
5. **Admin Database** — Click any column header. Verify 3-stage cycle (was 2-stage before).

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix: resolve any type or runtime issues in sortable tables"
```
