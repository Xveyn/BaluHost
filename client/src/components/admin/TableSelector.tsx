import { useState, useRef, useEffect, useMemo } from 'react'
import { Search, ChevronDown, Table, Database } from 'lucide-react'

interface Props {
  tables: string[]
  categories: Record<string, string[]>
  selected: string | null
  onSelect: (table: string) => void
  rowCounts?: Record<string, number>
}

export default function TableSelector({ tables, categories, selected, onSelect, rowCounts }: Props) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasCategories = Object.keys(categories).length > 0

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen])

  // Focus search input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  // Keyboard handling
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false)
      setSearch('')
    }
  }

  // Filter tables by search
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

  const handleSelect = (table: string) => {
    onSelect(table)
    setIsOpen(false)
    setSearch('')
  }

  const formatCount = (count: number) => {
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`
    return String(count)
  }

  return (
    <div ref={containerRef} className="relative" onKeyDown={handleKeyDown}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 w-full sm:w-72 bg-slate-800/60 border rounded-lg px-3 py-2 text-sm text-left transition-colors ${
          isOpen ? 'border-blue-500/50 ring-1 ring-blue-500/20' : 'border-slate-700/50 hover:border-slate-600/50'
        }`}
      >
        <Table className="w-4 h-4 text-slate-500 flex-shrink-0" />
        <span className={`flex-1 truncate ${selected ? 'text-slate-200' : 'text-slate-500'}`}>
          {selected || 'Select a table...'}
        </span>
        {selected && rowCounts?.[selected] !== undefined && (
          <span className="text-xs text-slate-500 flex-shrink-0">
            {rowCounts[selected].toLocaleString()} rows
          </span>
        )}
        <ChevronDown className={`w-4 h-4 text-slate-500 flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-20 top-full mt-1 w-full sm:w-80 bg-slate-800 border border-slate-700/50 rounded-lg shadow-2xl shadow-black/40 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-slate-700/50">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tables..."
                className="w-full bg-slate-900/60 border border-slate-700/40 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          {/* Table list */}
          <div className="max-h-72 overflow-y-auto overscroll-contain">
            {hasCategories ? (
              Object.keys(filteredCategories).length === 0 ? (
                <div className="px-3 py-4 text-xs text-slate-500 text-center">No tables match "{search}"</div>
              ) : (
                Object.entries(filteredCategories).map(([cat, tbls]) => (
                  <div key={cat}>
                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 font-semibold bg-slate-900/40 sticky top-0">
                      {cat}
                    </div>
                    {tbls.map(tbl => (
                      <button
                        key={tbl}
                        onClick={() => handleSelect(tbl)}
                        className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between gap-2 transition-colors ${
                          selected === tbl
                            ? 'bg-blue-500/15 text-blue-300'
                            : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
                        }`}
                      >
                        <span className="truncate">{tbl}</span>
                        {rowCounts?.[tbl] !== undefined && (
                          <span className="text-[10px] text-slate-500 flex-shrink-0 tabular-nums">
                            {formatCount(rowCounts[tbl])}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                ))
              )
            ) : (
              filteredTables.length === 0 ? (
                <div className="px-3 py-4 text-xs text-slate-500 text-center">No tables match "{search}"</div>
              ) : (
                filteredTables.map(tbl => (
                  <button
                    key={tbl}
                    onClick={() => handleSelect(tbl)}
                    className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between gap-2 transition-colors ${
                      selected === tbl
                        ? 'bg-blue-500/15 text-blue-300'
                        : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
                    }`}
                  >
                    <span className="truncate">{tbl}</span>
                    {rowCounts?.[tbl] !== undefined && (
                      <span className="text-[10px] text-slate-500 flex-shrink-0 tabular-nums">
                        {formatCount(rowCounts[tbl])}
                      </span>
                    )}
                  </button>
                ))
              )
            )}
          </div>

          {/* Footer with count */}
          <div className="px-3 py-1.5 border-t border-slate-700/50 text-[10px] text-slate-500 flex items-center gap-1.5">
            <Database className="w-3 h-3" />
            {tables.length} tables
          </div>
        </div>
      )}
    </div>
  )
}
