import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'
import DataTypeIndicator from './admin/DataTypeIndicator'
import { formatAdminValue } from '../lib/adminDbFormatters'

interface Column {
  name: string
  type?: string
}

interface Props {
  columns: Column[]
  rows: Array<Record<string, any>>
  tableName?: string
  page?: number
  pageSize?: number
  total?: number | null
  onPageChange?: (p: number) => void
  ownerMap?: Record<string, string>
  sortBy?: string | null
  sortOrder?: 'asc' | 'desc' | null
  onSortChange?: (column: string, order: 'asc' | 'desc') => void
  onRowClick?: (row: Record<string, any>) => void
}

export default function AdminDataTable({ columns, rows, ownerMap, sortBy, sortOrder, onSortChange, onRowClick }: Props) {
  const { t } = useTranslation('admin')
  const [isMobile, setIsMobile] = useState(false)

  // hide specific columns from display (e.g. parent_path, is_directory, mime_type)
  const visibleColumns = columns.filter((c) => {
    const n = c.name.toLowerCase()
    // hide hashed_password column explicitly (sensitive)
    return !n.includes('parent_path') && !n.includes('is_directory') && !n.includes('mime') && !n.includes('hashed_password')
  })

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 900)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // determine column behavior (wider path column, truncate others)
  const isPathColumn = (name: string) => name.toLowerCase().includes('path') || name.toLowerCase() === 'path'

  const columnMinWidthClass = (name: string) => {
    const n = name.toLowerCase()
    if (n === 'id' || n.endsWith('_id')) return 'min-w-[48px]'
    if (n === 'path' || n.includes('path')) return 'min-w-[220px]'
    if (n === 'name' || n.includes('name')) return 'min-w-[140px]'
    if (n.includes('size') || n.includes('bytes')) return 'min-w-[80px]'
    if (n.startsWith('is_') || n === 'is_directory' || n === 'directory') return 'min-w-[80px]'
    if (n.includes('mime') || n.includes('type')) return 'min-w-[120px]'
    if (n.includes('parent')) return 'min-w-[140px]'
    if (n.includes('created') || n.includes('updated') || n.includes('date') || n.includes('at')) return 'min-w-[160px]'
    return 'min-w-[120px]'
  }

  const formatValue = (name: string, raw: any) => formatAdminValue(name, raw, t)

  const cellAlignmentClass = (name: string) => {
    const n = name.toLowerCase()
    if (n.includes('size') || n.includes('bytes') || n === 'owner_id' || n.endsWith('_id')) return 'text-right'
    if (n.startsWith('is_') || n === 'is_directory') return 'text-center'
    return 'text-left'
  }

  const columnMaxWidthClass = (name: string) => {
    const n = name.toLowerCase()
    if (n === 'id' || n.endsWith('_id')) return 'max-w-[56px]'
    if (n === 'path' || n.includes('path')) return 'max-w-[240px]'
    if (n === 'name' || n.includes('name')) return 'max-w-[180px]'
    if (n.includes('size') || n.includes('bytes')) return 'max-w-[100px]'
    if (n.startsWith('is_') || n === 'is_directory' || n === 'directory') return 'max-w-[80px]'
    if (n.includes('mime') || n.includes('type')) return 'max-w-[140px]'
    if (n.includes('parent')) return 'max-w-[200px]'
    if (n.includes('created') || n.includes('updated') || n.includes('date') || n.includes('at')) return 'max-w-[180px]'
    return 'max-w-[140px]'
  }

  const preferredColPct = (name: string) => {
    const n = name.toLowerCase()
    if (n === 'id' || n.endsWith('_id')) return 4
    if (n === 'path' || n.includes('path')) return 26
    if (n === 'name' || n.includes('name')) return 18
    if (n.includes('size') || n.includes('bytes')) return 7
    if (n.startsWith('is_') || n === 'is_directory') return 5
    if (n.includes('mime') || n.includes('type')) return 8
    if (n.includes('parent')) return 8
    if (n.includes('created') || n.includes('updated') || n.includes('date') || n.includes('at')) return 14
    return 10
  }

  const computeColumnPercents = (cols: Column[]) => {
    const pcts = cols.map((c) => preferredColPct(c.name))
    const total = pcts.reduce((a, b) => a + b, 0)
    return pcts.map((p) => Math.max(3, Math.round((p / total) * 100)))
  }

  const handleHeaderClick = (colName: string) => {
    if (!onSortChange) return
    if (sortBy === colName) {
      onSortChange(colName, sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      onSortChange(colName, 'asc')
    }
  }

  const renderSortIcon = (colName: string) => {
    if (sortBy === colName) {
      return sortOrder === 'asc'
        ? <ArrowUp className="w-3 h-3 text-blue-400" />
        : <ArrowDown className="w-3 h-3 text-blue-400" />
    }
    return <ArrowUpDown className="w-3 h-3 text-slate-600 group-hover/th:text-slate-400 transition-colors" />
  }

  return (
    <div>
      <div className="px-0 sm:px-2 py-4 sm:py-5">
        {isMobile ? (
          <div className="space-y-3">
            {rows.map((r, idx) => (
              <div
                key={idx}
                className={`bg-slate-800/40 p-3 rounded border border-slate-800/60 ${onRowClick ? 'cursor-pointer hover:bg-slate-800/60 transition-colors' : ''}`}
                onClick={() => onRowClick?.(r)}
              >
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {visibleColumns.map((c) => {
                    const raw = r[c.name]
                    const text = raw === null || raw === undefined ? '-' : String(raw)
                    return (
                      <div key={c.name} className="py-1">
                        <div className="text-xs text-slate-400 uppercase tracking-wide">{c.name}</div>
                        <div className={`text-sm text-slate-100 ${isPathColumn(c.name) ? 'break-words' : 'truncate'}`}>{text}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto border border-slate-800/60 rounded min-w-0 px-4">
            <table className="w-full table-fixed min-w-0 divide-y divide-slate-800/60">
              <thead className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm">
                <tr className="text-left text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">
                  {(() => {
                    const pcts = computeColumnPercents(visibleColumns)
                    return visibleColumns.map((c, i) => (
                      <th
                        key={c.name}
                        className={`px-3 sm:px-5 py-2 sm:py-3 text-left group/th ${onSortChange ? 'cursor-pointer select-none hover:text-slate-300 transition-colors' : ''}`}
                        style={{ width: `${pcts[i]}%` }}
                        onClick={() => handleHeaderClick(c.name)}
                      >
                        <div className="flex items-center gap-1.5 overflow-hidden">
                          <span className="truncate min-w-0">{c.name.toLowerCase().includes('owner') ? 'OWNER' : c.name}</span>
                          {c.type && <DataTypeIndicator type={c.type} className="flex-shrink-0" />}
                          {onSortChange && <span className="flex-shrink-0">{renderSortIcon(c.name)}</span>}
                        </div>
                      </th>
                    ))
                  })()}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {rows.map((r, idx) => (
                  <tr
                    key={idx}
                    className={`group transition hover:bg-slate-900/65 ${onRowClick ? 'cursor-pointer hover:bg-blue-500/5' : ''}`}
                    onClick={() => onRowClick?.(r)}
                  >
                    {visibleColumns.map((c) => {
                      const raw = r[c.name]
                      const wclass = columnMinWidthClass(c.name)
                      const maxclass = columnMaxWidthClass(c.name)
                      const align = cellAlignmentClass(c.name)
                      let formatted = formatValue(c.name, raw)

                      // if this is an owner-like column, prefer mapped username
                      const cn = c.name.toLowerCase()
                      if (cn.includes('owner')) {
                        // raw might be an id, or an object like { id: 8 } or { user: { id: 8, username: '...' } }
                        let lookupKey: any = raw
                        if (raw && typeof raw === 'object') {
                          lookupKey = raw.id ?? raw.ID ?? raw.user_id ?? raw.userId ?? raw.owner_id ?? raw.ownerId
                        }
                        const name = ownerMap?.[String(lookupKey)]
                        if (name) formatted = name
                      }

                      // special visual for booleans
                      if (c.name.toLowerCase().startsWith('is_') || c.name.toLowerCase() === 'is_directory') {
                        return (
                          <td key={c.name} className={`px-3 sm:px-5 py-3 sm:py-4 text-xs sm:text-sm ${wclass} ${align}`}>
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] ${formatted === 'true' ? 'bg-emerald-600 text-white' : 'bg-slate-700 text-slate-300'}`}>{formatted}</span>
                          </td>
                        )
                      }

                      // Use truncation with tooltip for all columns
                      const cellContent = (
                        <div className={`overflow-hidden text-ellipsis whitespace-nowrap ${maxclass}`} title={formatted}>{formatted}</div>
                      )

                      return (
                        <td key={c.name} className={`px-3 sm:px-5 py-3 sm:py-4 text-xs sm:text-sm ${wclass} ${align}`}>
                          {cellContent}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
