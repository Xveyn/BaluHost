import { useState } from 'react'
import { X, Filter } from 'lucide-react'
import type { AdminTableSchemaField, ColumnFilter, ColumnFilters } from '../../lib/api'

interface Props {
  columns: AdminTableSchemaField[]
  filters: ColumnFilters
  onFiltersChange: (filters: ColumnFilters) => void
}

function getColumnCategory(type: string): 'string' | 'number' | 'boolean' | 'datetime' {
  const t = type.toUpperCase()
  if (t.includes('BOOL')) return 'boolean'
  if (t.includes('INT') || t.includes('FLOAT') || t.includes('REAL') || t.includes('NUMERIC') || t.includes('DECIMAL') || t.includes('DOUBLE')) return 'number'
  if (t.includes('DATE') || t.includes('TIME') || t.includes('TIMESTAMP')) return 'datetime'
  return 'string'
}

const NUMERIC_OPS = [
  { value: 'eq', label: '=' },
  { value: 'gt', label: '>' },
  { value: 'lt', label: '<' },
  { value: 'gte', label: '>=' },
  { value: 'lte', label: '<=' },
] as const

export default function ColumnFilterPanel({ columns, filters, onFiltersChange }: Props) {
  const [expandedCol, setExpandedCol] = useState<string | null>(null)

  // Filter out hidden/sensitive columns
  const filterableColumns = columns.filter(c => {
    const n = c.name.toLowerCase()
    return !n.includes('hashed_password') && !n.includes('parent_path') && !n.includes('is_directory') && !n.includes('mime')
  })

  const activeFilterCount = Object.keys(filters).length

  const updateFilter = (colName: string, filter: ColumnFilter | null) => {
    const next = { ...filters }
    if (filter) {
      next[colName] = filter
    } else {
      delete next[colName]
    }
    onFiltersChange(next)
  }

  const clearAll = () => {
    onFiltersChange({})
  }

  const renderFilterInput = (col: AdminTableSchemaField) => {
    const category = getColumnCategory(col.type)
    const current = filters[col.name]

    if (category === 'boolean') {
      const val = current?.op === 'is_true' ? 'true' : current?.op === 'is_false' ? 'false' : ''
      return (
        <select
          value={val}
          onChange={(e) => {
            const v = e.target.value
            if (v === 'true') updateFilter(col.name, { op: 'is_true' })
            else if (v === 'false') updateFilter(col.name, { op: 'is_false' })
            else updateFilter(col.name, null)
          }}
          className="w-full bg-slate-800 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50"
        >
          <option value="">All</option>
          <option value="true">True</option>
          <option value="false">False</option>
        </select>
      )
    }

    if (category === 'number') {
      const op = (current?.op as string) || 'eq'
      const value = current?.value ?? ''
      return (
        <div className="flex gap-2">
          <select
            value={op}
            onChange={(e) => {
              if (value !== '' && value !== undefined) {
                updateFilter(col.name, { op: e.target.value as ColumnFilter['op'], value: Number(value) })
              }
            }}
            className="bg-slate-800 border border-slate-600/50 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50 w-16"
          >
            {NUMERIC_OPS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <input
            type="number"
            value={value}
            placeholder="Value..."
            onChange={(e) => {
              const v = e.target.value
              if (v === '') {
                updateFilter(col.name, null)
              } else {
                updateFilter(col.name, { op: op as ColumnFilter['op'], value: Number(v) })
              }
            }}
            className="flex-1 bg-slate-800 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50"
          />
        </div>
      )
    }

    if (category === 'datetime') {
      const fromVal = (current?.from as string) ?? ''
      const toVal = (current?.to as string) ?? ''
      return (
        <div className="flex gap-2">
          <input
            type="datetime-local"
            value={fromVal}
            onChange={(e) => {
              const from = e.target.value || undefined
              const to = toVal || undefined
              if (!from && !to) {
                updateFilter(col.name, null)
              } else {
                updateFilter(col.name, { op: 'between', from, to })
              }
            }}
            className="flex-1 bg-slate-800 border border-slate-600/50 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50"
          />
          <span className="text-slate-500 self-center text-xs">to</span>
          <input
            type="datetime-local"
            value={toVal}
            onChange={(e) => {
              const from = fromVal || undefined
              const to = e.target.value || undefined
              if (!from && !to) {
                updateFilter(col.name, null)
              } else {
                updateFilter(col.name, { op: 'between', from, to })
              }
            }}
            className="flex-1 bg-slate-800 border border-slate-600/50 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50"
          />
        </div>
      )
    }

    // Default: string / contains
    const value = (current?.value as string) ?? ''
    return (
      <input
        type="text"
        value={value}
        placeholder={`Filter ${col.name}...`}
        onChange={(e) => {
          const v = e.target.value
          if (!v) {
            updateFilter(col.name, null)
          } else {
            updateFilter(col.name, { op: 'contains', value: v })
          }
        }}
        className="w-full bg-slate-800 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50"
      />
    )
  }

  return (
    <div className="bg-slate-900/40 border border-slate-700/50 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-slate-300">Column Filters</span>
          {activeFilterCount > 0 && (
            <span className="bg-blue-500/20 text-blue-400 text-xs font-bold px-2 py-0.5 rounded-full border border-blue-500/30">
              {activeFilterCount}
            </span>
          )}
        </div>
        {activeFilterCount > 0 && (
          <button
            onClick={clearAll}
            className="text-xs text-slate-400 hover:text-red-400 transition-colors flex items-center gap-1"
          >
            <X className="w-3 h-3" />
            Clear All
          </button>
        )}
      </div>

      {/* Filter Grid */}
      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {filterableColumns.map(col => {
          const hasFilter = !!filters[col.name]
          const category = getColumnCategory(col.type)
          const isExpanded = expandedCol === col.name || hasFilter

          return (
            <div
              key={col.name}
              className={`rounded-lg border transition-colors ${
                hasFilter
                  ? 'border-blue-500/40 bg-blue-500/5'
                  : 'border-slate-700/30 bg-slate-800/20 hover:border-slate-600/50'
              }`}
            >
              <button
                onClick={() => setExpandedCol(isExpanded && !hasFilter ? null : col.name)}
                className="w-full px-3 py-2 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`text-xs font-medium truncate ${hasFilter ? 'text-blue-300' : 'text-slate-400'}`}>
                    {col.name}
                  </span>
                  <span className="text-[10px] text-slate-600 uppercase">{category}</span>
                </div>
                {hasFilter && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      updateFilter(col.name, null)
                    }}
                    className="text-slate-500 hover:text-red-400 transition-colors p-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </button>
              {isExpanded && (
                <div className="px-3 pb-3">
                  {renderFilterInput(col)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
