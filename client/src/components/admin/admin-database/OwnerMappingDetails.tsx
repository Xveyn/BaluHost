import { RefreshCw } from 'lucide-react'
import type { OwnerLoadInfo } from '../../../hooks/useAdminDatabaseBrowse'

interface OwnerMappingDetailsProps {
  ownerLoadInfo: OwnerLoadInfo
  onLoad: () => void
}

/**
 * Collapsible owner-mapping panel with a status badge and a manual load button.
 * Extracted verbatim from AdminDatabase's browse view.
 */
export default function OwnerMappingDetails({ ownerLoadInfo, onLoad }: OwnerMappingDetailsProps) {
  return (
    <details className="mx-4 sm:mx-5 mt-3 group">
      <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1.5">
        <span className="text-[10px] transition-transform group-open:rotate-90">&#9654;</span>
        Owner Mapping
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
          ownerLoadInfo.status === 'loaded' ? 'bg-emerald-500/20 text-emerald-400' :
          ownerLoadInfo.status === 'loading' ? 'bg-blue-500/20 text-blue-400' :
          ownerLoadInfo.status === 'failed' ? 'bg-red-500/20 text-red-400' :
          'bg-slate-700/50 text-slate-500'
        }`}>
          {ownerLoadInfo.status}
        </span>
      </summary>
      <div className="mt-2 pl-5 pb-2 space-y-2 text-xs">
        {ownerLoadInfo.count !== undefined && (
          <p className="text-slate-500">{ownerLoadInfo.count} users loaded</p>
        )}
        {ownerLoadInfo.error && (
          <p className="text-red-400">Error: {ownerLoadInfo.error}</p>
        )}
        <button
          onClick={() => onLoad()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800/60 border border-slate-700/50 text-slate-300 hover:text-white hover:border-slate-600/50 transition-colors text-xs"
        >
          <RefreshCw className={`w-3 h-3 ${ownerLoadInfo.status === 'loading' ? 'animate-spin' : ''}`} />
          Load Owner Names
        </button>
      </div>
    </details>
  )
}
