import type { SortDirection } from '../../hooks/useSortableTable';

export type SharesTab = 'shares' | 'shared-with-me' | 'cloud-exports';

export interface SortProps {
  sortKey: string | null;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
}
