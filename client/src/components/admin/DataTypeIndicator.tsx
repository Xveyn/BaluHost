const TYPE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  INT: { bg: 'bg-blue-500/15 border-blue-500/30', text: 'text-blue-300', label: 'INT' },
  INTEGER: { bg: 'bg-blue-500/15 border-blue-500/30', text: 'text-blue-300', label: 'INT' },
  BIGINT: { bg: 'bg-blue-500/15 border-blue-500/30', text: 'text-blue-300', label: 'BIGINT' },
  SMALLINT: { bg: 'bg-blue-500/15 border-blue-500/30', text: 'text-blue-300', label: 'SMALL' },
  TEXT: { bg: 'bg-slate-500/15 border-slate-500/30', text: 'text-slate-300', label: 'TEXT' },
  VARCHAR: { bg: 'bg-slate-500/15 border-slate-500/30', text: 'text-slate-300', label: 'VARCHAR' },
  CHAR: { bg: 'bg-slate-500/15 border-slate-500/30', text: 'text-slate-300', label: 'CHAR' },
  BOOLEAN: { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-300', label: 'BOOL' },
  BOOL: { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-300', label: 'BOOL' },
  TIMESTAMP: { bg: 'bg-orange-500/15 border-orange-500/30', text: 'text-orange-300', label: 'TIME' },
  DATETIME: { bg: 'bg-orange-500/15 border-orange-500/30', text: 'text-orange-300', label: 'TIME' },
  DATE: { bg: 'bg-orange-500/15 border-orange-500/30', text: 'text-orange-300', label: 'DATE' },
  UUID: { bg: 'bg-purple-500/15 border-purple-500/30', text: 'text-purple-300', label: 'UUID' },
  FLOAT: { bg: 'bg-cyan-500/15 border-cyan-500/30', text: 'text-cyan-300', label: 'FLOAT' },
  REAL: { bg: 'bg-cyan-500/15 border-cyan-500/30', text: 'text-cyan-300', label: 'REAL' },
  DOUBLE: { bg: 'bg-cyan-500/15 border-cyan-500/30', text: 'text-cyan-300', label: 'DBL' },
  NUMERIC: { bg: 'bg-cyan-500/15 border-cyan-500/30', text: 'text-cyan-300', label: 'NUM' },
  DECIMAL: { bg: 'bg-cyan-500/15 border-cyan-500/30', text: 'text-cyan-300', label: 'DEC' },
  JSON: { bg: 'bg-amber-500/15 border-amber-500/30', text: 'text-amber-300', label: 'JSON' },
  JSONB: { bg: 'bg-amber-500/15 border-amber-500/30', text: 'text-amber-300', label: 'JSONB' },
  BLOB: { bg: 'bg-rose-500/15 border-rose-500/30', text: 'text-rose-300', label: 'BLOB' },
  BYTEA: { bg: 'bg-rose-500/15 border-rose-500/30', text: 'text-rose-300', label: 'BYTES' },
}

const DEFAULT_STYLE = { bg: 'bg-slate-500/10 border-slate-600/30', text: 'text-slate-400', label: '' }

function resolveStyle(rawType: string) {
  const upper = rawType.toUpperCase().trim()
  // Direct match first
  if (TYPE_STYLES[upper]) return TYPE_STYLES[upper]
  // Partial match (e.g. "CHARACTER VARYING" → VARCHAR, "TIMESTAMP WITHOUT TIME ZONE" → TIMESTAMP)
  for (const [key, style] of Object.entries(TYPE_STYLES)) {
    if (upper.includes(key)) return style
  }
  return { ...DEFAULT_STYLE, label: upper.slice(0, 6) }
}

interface DataTypeIndicatorProps {
  type: string
  className?: string
}

export default function DataTypeIndicator({ type, className }: DataTypeIndicatorProps) {
  const style = resolveStyle(type)
  return (
    <span
      className={`inline-flex items-center rounded border px-1 py-px text-[9px] font-medium leading-tight tracking-wide ${style.bg} ${style.text} ${className ?? ''}`}
    >
      {style.label}
    </span>
  )
}
