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
