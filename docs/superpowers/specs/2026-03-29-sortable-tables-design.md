# Sortable Tables Design

**Date:** 2026-03-29
**Scope:** Client-side sortable column headers for frontend tables

## Problem

Most tables in the frontend have static column headers. Users cannot sort data by clicking column headers. The `AdminDataTable` has sorting but only a 2-stage cycle (asc/desc) and relies on backend sorting. A consistent, reusable client-side sorting system is needed.

## Design

### Shared Infrastructure

#### `useSortableTable<T>` Hook

Location: `client/src/hooks/useSortableTable.ts`

```typescript
type SortDirection = 'asc' | 'desc' | null;

interface SortState {
  key: string | null;
  direction: SortDirection;
}

function useSortableTable<T>(
  data: T[],
  options?: {
    defaultSort?: { key: string; direction: 'asc' | 'desc' };
    getValueForSort?: Record<string, (item: T) => string | number | boolean | Date | null>;
  }
): {
  sortedData: T[];
  sortKey: string | null;
  sortDirection: SortDirection;
  toggleSort: (key: string) => void;
  resetSort: () => void;
}
```

**3-stage cycle:** Each click on the same column cycles: `null -> 'asc' -> 'desc' -> null`. Clicking a different column starts at `'asc'` and resets the previous.

**Sort logic by data type** (auto-detected from first non-null value):
- **string**: `localeCompare()` (case-insensitive)
- **number**: numeric comparison
- **Date / ISO string**: parse to timestamp, compare numerically
- **boolean**: false < true
- **null/undefined**: always sorted to the end

`getValueForSort` allows custom value extraction for nested/computed columns (e.g., `file_name` from a file object displayed as a rich cell).

#### `SortableHeader` Component

Location: `client/src/components/ui/SortableHeader.tsx`

```typescript
interface SortableHeaderProps {
  label: string;
  sortKey: string;
  activeSortKey: string | null;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
  className?: string;
}
```

Renders a `<th>` with:
- Click handler calling `onSort(sortKey)`
- Icon: `ArrowUp` (asc), `ArrowDown` (desc), `ArrowUpDown` (inactive) from lucide-react
- Hover state for inactive headers
- Matches existing header styling patterns (text-xs, uppercase, tracking-wider, text-slate-400/500)

Non-sortable columns continue using plain `<th>` elements (e.g., Actions, Checkbox columns).

### Target Tables

#### 1. FileListView (`components/file-manager/FileListView.tsx`)

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| Name | `name` | string | `file.name` |
| Type | -- | -- | Not sortable (directory vs file grouping is better handled by default order) |
| Size | `size` | number | `file.size` (bytes) |
| Modified | `modified` | date | `file.modified` (ISO string) |
| Owner | `owner` | string | Resolved via `renderOwnerName()` helper, use `getValueForSort` |

**Integration:** The parent component (`FileManager`) passes `files` array. Add `useSortableTable` in `FileListView`, wrap the `files` prop. Desktop table headers become `SortableHeader`. Mobile card view uses `sortedData` but no header interaction (cards don't have headers).

#### 2. SharesPage (`pages/SharesPage.tsx`)

Three sub-tables, each gets its own `useSortableTable` instance:

**My Shares tab:**

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| File | `file_name` | string | |
| Owner | `owner_username` | string | |
| Shared With | `shared_with_username` | string | |
| Permissions | -- | -- | Not sortable (badge combination) |
| Expires | `expires_at` | date | |
| Actions | -- | -- | Not sortable |

**Shared With Me tab:**

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| File | `file_name` | string | |
| Owner | `owner_username` | string | |
| Permissions | -- | -- | Not sortable |
| Shared | `shared_at` | date | |
| Expires | `expires_at` | date | |

**Cloud Exports tab:**

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| Provider | `provider` | string | Use `getValueForSort` with `getProviderLabel()` |
| File | `file_name` | string | |
| Link | -- | -- | Not sortable |
| Status | `status` | string | |
| Created | `created_at` | date | |
| Expires | `expires_at` | date | |
| Actions | -- | -- | Not sortable |

#### 3. UserTable (`components/user-management/UserTable.tsx`)

Currently has partial 2-stage sorting on 3 columns. Upgrade to 3-stage cycle on all data columns.

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| Checkbox | -- | -- | Not sortable |
| Username | `username` | string | Already sortable, upgrade cycle |
| Email | `email` | string | Currently not sortable, add |
| Role | `role` | string | Already sortable, upgrade cycle |
| Status | `is_active` | boolean | Currently not sortable, add |
| Created | `created_at` | date | Already sortable, upgrade cycle |
| Actions | -- | -- | Not sortable |

**Note:** UserTable receives pre-sorted `users` from parent. The sorting must move into UserTable itself or the parent must pass raw data. Since the parent (`UserManagement`) currently does its own sort, the cleanest approach is to use `useSortableTable` in the parent and pass `sortedData` + sort state as props, keeping UserTable as a presentation component.

#### 4. PiholeLocalDns (`components/pihole/PiholeLocalDns.tsx`)

| Column | Sort Key | Data Type | Notes |
|--------|----------|-----------|-------|
| Domain | `domain` | string | |
| IP | `ip` | string | |
| Actions | -- | -- | Not sortable |

### Retrofit: AdminDataTable 3-Stage Cycle

`AdminDataTable.tsx` currently cycles asc -> desc only. Update `handleHeaderClick` to support the 3-stage cycle: clicking a column that is currently `desc` resets to null (default). This is a small change in the existing `handleHeaderClick` logic and the parent `AdminDatabase.tsx` state management.

### What Does NOT Change

- Mobile card views: they render `sortedData` in sorted order but have no clickable headers
- Backend APIs: no changes, all sorting is client-side
- Tables not in scope (HistoryTable, SleepHistoryTable, ExecutionHistoryTable, etc.) -- these can adopt the hook later

## Testing

Manual verification per table:
1. Click header -> sorts ascending (icon: ArrowUp)
2. Click same header -> sorts descending (icon: ArrowDown)
3. Click same header -> resets to default order (icon: ArrowUpDown)
4. Click different header -> new column ascending, previous resets
5. String sort is case-insensitive
6. Date sort handles null dates (sorted to end)
7. Number sort works correctly for file sizes
