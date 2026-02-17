import { X } from 'lucide-react'
import DataTypeIndicator from './DataTypeIndicator'
import { formatAdminValue } from '../../lib/adminDbFormatters'
import { useTranslation } from 'react-i18next'

interface Column {
  name: string
  type?: string
  nullable?: boolean
}

interface Props {
  row: Record<string, any>
  columns: Column[]
  onClose: () => void
  ownerMap?: Record<string, string>
}

export default function RowDetailPanel({ row, columns, onClose, ownerMap }: Props) {
  const { t } = useTranslation('admin')

  const resolveValue = (col: Column, raw: any): string => {
    const cn = col.name.toLowerCase()
    // Owner column resolution
    if (cn.includes('owner') && ownerMap) {
      let lookupKey: any = raw
      if (raw && typeof raw === 'object') {
        lookupKey = raw.id ?? raw.ID ?? raw.user_id ?? raw.userId ?? raw.owner_id ?? raw.ownerId
      }
      const name = ownerMap[String(lookupKey)]
      if (name) return name
    }
    return formatAdminValue(col.name, raw, t)
  }

  // Hide sensitive columns
  const visibleColumns = columns.filter((c) => {
    const n = c.name.toLowerCase()
    return !n.includes('hashed_password')
  })

  return (
    <>
      {/* Desktop: side panel */}
      <div className="hidden lg:flex flex-col w-80 shrink-0 card !p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60">
          <h3 className="text-sm font-semibold text-white">Row Detail</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
          {visibleColumns.map((col) => (
            <div key={col.name}>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[11px] text-slate-400 font-medium">{col.name}</span>
                {col.type && <DataTypeIndicator type={col.type} />}
                {col.nullable && (
                  <span className="text-[9px] text-slate-600 border border-slate-700/40 rounded px-1 py-px">NULL</span>
                )}
              </div>
              <div className="text-sm text-slate-200 break-words bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-700/30">
                {resolveValue(col, row[col.name])}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Mobile: bottom sheet */}
      <div className="lg:hidden fixed inset-0 z-50">
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
        <div className="absolute bottom-0 left-0 right-0 max-h-[70vh] bg-slate-900 border-t border-slate-700/50 rounded-t-2xl overflow-hidden flex flex-col animate-slide-up">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60 shrink-0">
            <h3 className="text-sm font-semibold text-white">Row Detail</h3>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
            {visibleColumns.map((col) => (
              <div key={col.name}>
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[11px] text-slate-400 font-medium">{col.name}</span>
                  {col.type && <DataTypeIndicator type={col.type} />}
                  {col.nullable && (
                    <span className="text-[9px] text-slate-600 border border-slate-700/40 rounded px-1 py-px">NULL</span>
                  )}
                </div>
                <div className="text-sm text-slate-200 break-words bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-700/30">
                  {resolveValue(col, row[col.name])}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
