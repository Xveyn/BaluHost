import { Download, ChevronLeft, ChevronRight, Search, Filter, X } from 'lucide-react'
import TableSelector from '../TableSelector'

interface BrowseToolbarProps {
  tables: string[]
  categories: Record<string, string[]>
  selected: string | null
  onTableSelect: (tableName: string) => void
  globalSearch: string
  onGlobalSearchChange: (value: string) => void
  onClearGlobalSearch: () => void
  columnCount: number
  showFilters: boolean
  onToggleFilters: () => void
  activeFilterCount: number
  pageSize: number
  onPageSizeChange: (size: number) => void
  page: number
  totalPages: number | null
  onPageChange: (page: number) => void
  rowCount: number
  onCsvExport: () => void
  total: number | null
  rangeStart: number
  rangeEnd: number
}

/**
 * Browse-view toolbar: mobile table selector, global search, filter toggle,
 * page-size selector, pagination, CSV export and the row-count readout.
 * Extracted verbatim from AdminDatabase's browse view.
 */
export default function BrowseToolbar({
  tables,
  categories,
  selected,
  onTableSelect,
  globalSearch,
  onGlobalSearchChange,
  onClearGlobalSearch,
  columnCount,
  showFilters,
  onToggleFilters,
  activeFilterCount,
  pageSize,
  onPageSizeChange,
  page,
  totalPages,
  onPageChange,
  rowCount,
  onCsvExport,
  total,
  rangeStart,
  rangeEnd,
}: BrowseToolbarProps) {
  return (
    <div className="px-4 sm:px-5 py-3 border-b border-slate-800/60">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
        {/* Mobile-only table selector dropdown */}
        <div className="lg:hidden">
          <TableSelector
            tables={tables}
            categories={categories}
            selected={selected}
            onSelect={onTableSelect}
          />
        </div>

        {/* Global Search */}
        {selected && (
          <div className="relative w-full sm:flex-1 sm:min-w-[160px] sm:max-w-xs sm:w-auto">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              value={globalSearch}
              onChange={(e) => onGlobalSearchChange(e.target.value)}
              placeholder="Search columns..."
              className="w-full bg-slate-800/60 border border-slate-700/50 rounded-lg pl-8 pr-8 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
            />
            {globalSearch && (
              <button
                onClick={onClearGlobalSearch}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}

        {/* Filter Toggle */}
        {selected && columnCount > 0 && (
          <button
            onClick={onToggleFilters}
            className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 border touch-manipulation active:scale-95 ${
              showFilters || activeFilterCount > 0
                ? 'bg-blue-500/10 border-blue-500/40 text-blue-300'
                : 'bg-slate-800/60 border-slate-700/50 text-slate-300 hover:bg-slate-700/50 hover:text-white'
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Filters</span>
            {activeFilterCount > 0 && (
              <span className="bg-blue-500 text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
          </button>
        )}

        {/* Pagination + PageSize + Export wrapper */}
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
          {/* Page Size Selector */}
          {selected && (
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="bg-slate-800/60 border border-slate-700/50 rounded-lg px-2 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 transition-colors min-h-[36px] touch-manipulation"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          )}

          {/* Pagination */}
          {selected && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => onPageChange(Math.max(1, page - 1))}
                className={`p-2 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-md border transition-all duration-200 touch-manipulation active:scale-95 ${
                  page <= 1
                    ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                    : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:text-white'
                }`}
                disabled={page <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-slate-300 font-medium min-w-[60px] text-center tabular-nums">
                {page}{totalPages ? ` / ${totalPages}` : ''}
              </span>
              <button
                onClick={() => onPageChange(page + 1)}
                className={`p-2 min-h-[36px] min-w-[36px] flex items-center justify-center rounded-md border transition-all duration-200 touch-manipulation active:scale-95 ${
                  totalPages !== null && page >= (totalPages ?? 1)
                    ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                    : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:text-white'
                }`}
                disabled={totalPages !== null && page >= (totalPages ?? 1)}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Export Button */}
          <button
            disabled={!selected || rowCount === 0}
            className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 touch-manipulation active:scale-95 ${
              selected && rowCount
                ? 'bg-blue-500/20 border border-blue-500/40 text-blue-300 hover:bg-blue-500/30'
                : 'bg-slate-700/40 text-slate-500 cursor-not-allowed border border-slate-700/50'
            }`}
            onClick={onCsvExport}
          >
            <Download className="w-3.5 h-3.5" />
            CSV
          </button>
        </div>

        {/* Row count info */}
        {selected && total !== null && (
          <>
            <span className="text-[11px] text-slate-500 ml-auto hidden sm:inline tabular-nums">
              {rangeStart}–{rangeEnd} von {total.toLocaleString()} · {columnCount} columns
            </span>
            <span className="text-[11px] text-slate-500 sm:hidden tabular-nums">
              {rangeStart}–{rangeEnd} / {total.toLocaleString()}
            </span>
          </>
        )}
      </div>
    </div>
  )
}
