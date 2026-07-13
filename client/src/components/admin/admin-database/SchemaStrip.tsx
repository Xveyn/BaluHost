import DataTypeIndicator from '../DataTypeIndicator'
import type { AdminTableSchemaField } from '../../../api/admin-db'

interface SchemaStripProps {
  columns: AdminTableSchemaField[]
}

/**
 * Always-visible strip of column-name + type badges for the selected table.
 * Extracted verbatim from AdminDatabase's browse view.
 */
export default function SchemaStrip({ columns }: SchemaStripProps) {
  return (
    <div className="mx-4 sm:mx-5 mt-3 flex flex-wrap gap-1.5">
      {columns.map((col) => (
        <span
          key={col.name}
          className={`inline-flex items-center gap-1 bg-slate-800/60 border border-slate-700/40 rounded-md px-2 py-1 text-xs ${
            col.nullable ? 'opacity-70' : ''
          }`}
        >
          <span className="text-slate-300">{col.name}</span>
          <DataTypeIndicator type={col.type} />
          {col.nullable && <span className="text-slate-600 text-[10px]">?</span>}
        </span>
      ))}
    </div>
  )
}
