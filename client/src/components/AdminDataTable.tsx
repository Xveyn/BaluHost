import React, { useEffect, useState } from 'react'

interface Column {
  name: string
  type?: string
}

interface Props {
  columns: Column[]
  rows: Array<Record<string, any>>
  tableName?: string
  page: number
  pageSize: number
  total?: number | null
  onPageChange?: (p: number) => void
  ownerMap?: Record<string, string>
}

export default function AdminDataTable({ columns, rows, tableName, page, pageSize, total, onPageChange, ownerMap }: Props) {
  const totalPages = total ? Math.ceil((total ?? 0) / pageSize) : null
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

  const formatValue = (name: string, raw: any) => {
    if (raw === null || raw === undefined) return '-'
    const n = name.toLowerCase()
    // sizes / numbers
    if (n.includes('size') || n.includes('bytes') || n === 'owner_id' || n.endsWith('_id')) {
      if (typeof raw === 'number') return new Intl.NumberFormat().format(raw)
      const num = Number(raw)
      return Number.isFinite(num) ? new Intl.NumberFormat().format(num) : String(raw)
    }

    // booleans
    if (n.startsWith('is_') || n === 'is_directory' || typeof raw === 'boolean') {
      return raw ? 'true' : 'false'
    }

    // dates
    if (n.includes('created') || n.includes('updated') || n.includes('date') || n.includes('at')) {
      const d = new Date(raw)
      if (!isNaN(d.getTime())) return d.toLocaleString()
    }

    return String(raw)
  }

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

  return (
    <div>
      <div className="px-0 sm:px-2 py-4 sm:py-5">
        {isMobile ? (
          <div className="space-y-3">
            {rows.map((r, idx) => (
              <div key={idx} className="bg-slate-800/40 p-3 rounded border border-slate-800/60">
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
              <thead>
                <tr className="text-left text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500 bg-transparent">
                  {(() => {
                    const pcts = computeColumnPercents(visibleColumns)
                    return visibleColumns.map((c, i) => (
                      <th
                        key={c.name}
                        className={`px-3 sm:px-5 py-2 sm:py-3 text-left`}
                        style={{ width: `${pcts[i]}%` }}
                      >
                        {c.name.toLowerCase().includes('owner') ? 'OWNER' : c.name}
                      </th>
                    ))
                  })()}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {rows.map((r, idx) => (
                  <tr key={idx} className="group transition hover:bg-slate-900/65">
                    {visibleColumns.map((c) => {
                      const raw = r[c.name]
                      const text = raw === null || raw === undefined ? '-' : String(raw)
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

                      // Use truncation with tooltip for all columns; compute content box
                      const cellContent = (
                        <div className={`overflow-hidden text-ellipsis whitespace-nowrap ${maxclass}`} title={formatted}>{formatted}</div>
                      )

                      if (c.name.toLowerCase().startsWith('is_') || c.name.toLowerCase() === 'is_directory') {
                        return (
                          <td key={c.name} className={`px-3 sm:px-5 py-3 sm:py-4 text-xs sm:text-sm ${wclass} ${align}`}>
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] ${formatted === 'true' ? 'bg-emerald-600 text-white' : 'bg-slate-700 text-slate-300'}`}>{formatted}</span>
                          </td>
                        )
                      }

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
