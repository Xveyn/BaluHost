import { useState, useMemo } from 'react'
import { Search, Database } from 'lucide-react'

interface Props {
  tables: string[]
  categories: Record<string, string[]>
  selected: string | null
  onSelect: (table: string) => void
}

export default function TableSidebar({ tables, categories, selected, onSelect }: Props) {
  const [search, setSearch] = useState('')

  const hasCategories = Object.keys(categories).length > 0

  const filteredCategories = useMemo(() => {
    const q = search.toLowerCase().trim()
    if (!q) return categories
    const result: Record<string, string[]> = {}
    for (const [cat, tbls] of Object.entries(categories)) {
      const matched = tbls.filter(t => t.toLowerCase().includes(q))
      if (matched.length > 0) result[cat] = matched
    }
    return result
  }, [categories, search])

  const filteredTables = useMemo(() => {
    const q = search.toLowerCase().trim()
    if (!q) return tables
    return tables.filter(t => t.toLowerCase().includes(q))
  }, [tables, search])

  const totalVisible = hasCategories
    ? Object.values(filteredCategories).reduce((s, a) => s + a.length, 0)
    : filteredTables.length

  return (
    <div className="hidden lg:flex flex-col w-56 xl:w-64 shrink-0 card !p-0 overflow-hidden">
      {/* Search */}
      <div className="p-3 border-b border-slate-800/60">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tables..."
            className="w-full bg-slate-800/60 border border-slate-700/40 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
          />
        </div>
      </div>

      {/* Table list */}
      <div className="flex-1 overflow-y-auto overscroll-contain min-h-0">
        {hasCategories ? (
          Object.keys(filteredCategories).length === 0 ? (
            <div className="px-3 py-6 text-xs text-slate-500 text-center">No tables match &quot;{search}&quot;</div>
          ) : (
            Object.entries(filteredCategories).map(([cat, tbls]) => (
              <div key={cat}>
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 font-semibold bg-slate-900/60 sticky top-0 z-[1]">
                  {cat}
                </div>
                {tbls.map(tbl => (
                  <button
                    key={tbl}
                    onClick={() => onSelect(tbl)}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors border-r-2 ${
                      selected === tbl
                        ? 'border-r-blue-400 bg-blue-500/15 text-blue-300'
                        : 'border-r-transparent text-slate-300 hover:bg-slate-800/50 hover:text-white'
                    }`}
                  >
                    <span className="truncate block">{tbl}</span>
                  </button>
                ))}
              </div>
            ))
          )
        ) : (
          filteredTables.length === 0 ? (
            <div className="px-3 py-6 text-xs text-slate-500 text-center">No tables match &quot;{search}&quot;</div>
          ) : (
            filteredTables.map(tbl => (
              <button
                key={tbl}
                onClick={() => onSelect(tbl)}
                className={`w-full text-left px-3 py-1.5 text-xs transition-colors border-r-2 ${
                  selected === tbl
                    ? 'border-r-blue-400 bg-blue-500/15 text-blue-300'
                    : 'border-r-transparent text-slate-300 hover:bg-slate-800/50 hover:text-white'
                }`}
              >
                <span className="truncate block">{tbl}</span>
              </button>
            ))
          )
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-slate-800/60 text-[10px] text-slate-500 flex items-center gap-1.5">
        <Database className="w-3 h-3" />
        {totalVisible === tables.length ? `${tables.length} tables` : `${totalVisible} / ${tables.length}`}
      </div>
    </div>
  )
}
