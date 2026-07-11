import { Search, Check, ArrowRight, AlertTriangle } from 'lucide-react';
import { formatBytes } from '../../../api/vcl';
import type { ReconciliationPreview } from '../../../types/vcl';

export function VclReconciliationCard({
  reconPreview,
  reconLoading,
  forceOverQuota,
  onScan,
  onForceChange,
  onApply,
}: {
  reconPreview: ReconciliationPreview | null;
  reconLoading: boolean;
  forceOverQuota: boolean;
  onScan: () => void;
  onForceChange: (v: boolean) => void;
  onApply: () => void;
}) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Search className="w-5 h-5 text-sky-400" />
        Ownership Reconciliation
      </h3>
      <p className="text-sm text-slate-400 mb-4">
        Scan for version ownership mismatches (e.g. after file transfers) and fix them.
      </p>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <button
          onClick={onScan}
          disabled={reconLoading}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <Search className={`w-4 h-4 ${reconLoading ? 'animate-spin' : ''}`} />
          Scan for Mismatches
        </button>
        {reconPreview && reconPreview.total_mismatches > 0 && (
          <>
            <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={forceOverQuota}
                onChange={(e) => onForceChange(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-slate-800"
              />
              Force even if quota exceeded
            </label>
            <button
              onClick={onApply}
              disabled={reconLoading}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <Check className="w-4 h-4" />
              Apply ({reconPreview.total_mismatches} versions)
            </button>
          </>
        )}
      </div>

      {reconPreview && reconPreview.total_mismatches > 0 && (
        <div className="space-y-4">
          {/* Affected Users Summary */}
          {reconPreview.affected_users.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-slate-300">Quota Impact</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {reconPreview.affected_users.map((u) => (
                  <div
                    key={u.user_id}
                    className={`p-3 rounded-lg border text-sm ${
                      u.would_exceed_quota
                        ? 'border-amber-500/30 bg-amber-500/10'
                        : 'border-slate-800 bg-slate-800/50'
                    }`}
                  >
                    <span className="font-medium text-white">{u.username}</span>
                    <span className="text-slate-400 ml-2">
                      {u.quota_delta > 0 ? '+' : ''}{formatBytes(Math.abs(u.quota_delta))}
                    </span>
                    {u.would_exceed_quota && (
                      <span className="ml-2 text-amber-400 text-xs flex items-center gap-1 inline-flex">
                        <AlertTriangle className="w-3 h-3" /> exceeds quota
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mismatch Table */}
          <div className="overflow-x-auto max-h-64 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr className="text-left border-b border-slate-800">
                  <th className="pb-2 text-slate-400 font-medium">File</th>
                  <th className="pb-2 text-slate-400 font-medium">Version</th>
                  <th className="pb-2 text-slate-400 font-medium">Current Owner</th>
                  <th className="pb-2 text-slate-400 font-medium"></th>
                  <th className="pb-2 text-slate-400 font-medium">File Owner</th>
                  <th className="pb-2 text-slate-400 font-medium">Size</th>
                </tr>
              </thead>
              <tbody>
                {reconPreview.mismatches.slice(0, 100).map((m) => (
                  <tr key={m.version_id} className="border-b border-slate-800/30">
                    <td className="py-1.5 text-slate-300 max-w-[200px] truncate" title={m.file_path}>
                      {m.file_path.split('/').pop()}
                    </td>
                    <td className="py-1.5 text-slate-400">v{m.version_number}</td>
                    <td className="py-1.5 text-red-300">{m.current_version_username}</td>
                    <td className="py-1.5 text-slate-500"><ArrowRight className="w-3 h-3" /></td>
                    <td className="py-1.5 text-green-300">{m.current_file_owner_username}</td>
                    <td className="py-1.5 text-slate-400">{formatBytes(m.compressed_size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {reconPreview.total_mismatches > 100 && (
              <p className="text-xs text-slate-500 mt-2">
                Showing 100 of {reconPreview.total_mismatches} mismatches
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
