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
