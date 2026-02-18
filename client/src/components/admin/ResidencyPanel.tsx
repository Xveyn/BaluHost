/**
 * ResidencyPanel component -- Admin panel for scanning and fixing residency violations.
 */

import { useState } from 'react';
import { AlertTriangle, CheckCircle, Loader2, Search, Wrench, FileWarning } from 'lucide-react';
import { enforceResidency, type ResidencyViolation } from '../../lib/api';

interface ResidencyPanelProps {
  onClose?: () => void;
}

export function ResidencyPanel({ onClose }: ResidencyPanelProps) {
  const [violations, setViolations] = useState<ResidencyViolation[]>([]);
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixedCount, setFixedCount] = useState(0);
  const [scanned, setScanned] = useState(false);
  const [scope, setScope] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const handleScan = async () => {
    setLoading(true);
    setError(null);
    setFixedCount(0);

    try {
      const result = await enforceResidency({
        dry_run: true,
        scope: scope || null,
      });
      setViolations(result.violations);
      setScanned(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        message = detail.map((e: any) => e.msg ?? String(e)).join('; ');
      } else {
        message = err?.message || 'Scan failed';
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleFix = async () => {
    setFixing(true);
    setError(null);

    try {
      const result = await enforceResidency({
        dry_run: false,
        scope: scope || null,
      });
      setViolations(result.violations);
      setFixedCount(result.fixed_count);
      setScanned(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        message = detail.map((e: any) => e.msg ?? String(e)).join('; ');
      } else {
        message = err?.message || 'Fix failed';
      }
      setError(message);
    } finally {
      setFixing(false);
    }
  };

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800/60">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
            <FileWarning className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">Residency Enforcement</h3>
            <p className="text-xs text-slate-400">Scan for files that violate the user-directory ownership invariant</p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            ×
          </button>
        )}
      </div>

      <div className="mt-5 space-y-4">
        {/* Scope Input */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Scope (optional)
          </label>
          <input
            type="text"
            value={scope}
            onChange={e => setScope(e.target.value)}
            placeholder="Leave empty to scan all users, or enter username"
            className="input w-full"
            disabled={loading || fixing}
          />
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleScan}
            disabled={loading || fixing}
            className="btn-secondary"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Scanning...</span>
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                <span>Scan (Dry Run)</span>
              </>
            )}
          </button>
          <button
            onClick={handleFix}
            disabled={loading || fixing || violations.length === 0}
            className="btn-primary"
          >
            {fixing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Fixing...</span>
              </>
            ) : (
              <>
                <Wrench className="w-4 h-4" />
                <span>Fix All</span>
              </>
            )}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
            {error}
          </div>
        )}

        {/* Results */}
        {scanned && (
          <div className="space-y-3">
            {/* Summary */}
            <div className={`p-3 rounded-lg border ${
              violations.length === 0
                ? 'bg-emerald-500/10 border-emerald-500/30'
                : 'bg-amber-500/10 border-amber-500/30'
            }`}>
              <div className="flex items-center gap-2">
                {violations.length === 0 ? (
                  <>
                    <CheckCircle className="w-5 h-5 text-emerald-400" />
                    <span className="text-emerald-300">No violations found</span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-5 h-5 text-amber-400" />
                    <span className="text-amber-300">
                      {violations.length} violation(s) found
                      {fixedCount > 0 && ` (${fixedCount} fixed)`}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Violations List */}
            {violations.length > 0 && (
              <div className="rounded-lg border border-slate-800/60 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-800/50 text-slate-400 text-left">
                      <th className="px-4 py-2 font-medium">Path</th>
                      <th className="px-4 py-2 font-medium">Owner</th>
                      <th className="px-4 py-2 font-medium">Actual Dir</th>
                      <th className="px-4 py-2 font-medium">Expected Dir</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {violations.slice(0, 50).map((v, idx) => (
                      <tr key={idx} className="text-slate-300 hover:bg-slate-800/30">
                        <td className="px-4 py-2 font-mono text-xs truncate max-w-[300px]" title={v.path}>
                          {v.path}
                        </td>
                        <td className="px-4 py-2">
                          <span className="text-sky-400">{v.current_owner_username}</span>
                          <span className="text-slate-500 text-xs ml-1">(ID {v.current_owner_id})</span>
                        </td>
                        <td className="px-4 py-2 text-rose-300 font-mono text-xs">{v.actual_directory}</td>
                        <td className="px-4 py-2 text-emerald-300 font-mono text-xs">{v.expected_directory}</td>
                      </tr>
                    ))}
                    {violations.length > 50 && (
                      <tr>
                        <td colSpan={4} className="px-4 py-2 text-center text-slate-500 text-xs">
                          ...and {violations.length - 50} more
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
