/**
 * Sleep History Table - Shows sleep state change history.
 */

import { useState, useEffect } from 'react';
import { History, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  getSleepHistory,
  SLEEP_STATE_INFO,
  TRIGGER_LABELS,
  type SleepHistoryEntry,
} from '../../api/sleep';

export function SleepHistoryTable() {
  const [entries, setEntries] = useState<SleepHistoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const pageSize = 20;

  useEffect(() => {
    loadHistory();
  }, [offset]);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await getSleepHistory(pageSize, offset);
      setEntries(data.entries);
      setTotal(data.total);
    } catch {
      // Silent
    } finally {
      setLoading(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);
  const currentPage = Math.floor(offset / pageSize) + 1;

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6">
      <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
        <History className="h-4 w-4 text-slate-400" />
        State Change History
        {total > 0 && (
          <span className="text-xs text-slate-500">({total} entries)</span>
        )}
      </h4>

      {loading ? (
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-8 bg-slate-700/50 rounded" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">
          No sleep state changes recorded yet.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="py-2 pr-3">Time</th>
                  <th className="py-2 pr-3">Transition</th>
                  <th className="py-2 pr-3">Trigger</th>
                  <th className="py-2 pr-3">Reason</th>
                  <th className="py-2 text-right">Duration</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const fromInfo = SLEEP_STATE_INFO[entry.previous_state] || { label: entry.previous_state, color: 'text-slate-400' };
                  const toInfo = SLEEP_STATE_INFO[entry.new_state] || { label: entry.new_state, color: 'text-slate-400' };

                  return (
                    <tr key={entry.id} className="border-b border-slate-800/50">
                      <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">
                        {new Date(entry.timestamp).toLocaleString()}
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        <span className={`text-xs ${fromInfo.color}`}>{fromInfo.label}</span>
                        <span className="text-slate-600 mx-1">{'\u2192'}</span>
                        <span className={`text-xs ${toInfo.color}`}>{toInfo.label}</span>
                      </td>
                      <td className="py-2 pr-3">
                        <span className="inline-flex items-center rounded-full bg-slate-800/50 px-2 py-0.5 text-[10px] text-slate-400">
                          {TRIGGER_LABELS[entry.triggered_by] || entry.triggered_by}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-xs text-slate-400 max-w-[200px] truncate" title={entry.reason}>
                        {entry.reason}
                      </td>
                      <td className="py-2 text-right text-xs text-slate-500 whitespace-nowrap">
                        {entry.duration_seconds != null
                          ? formatDuration(entry.duration_seconds)
                          : '\u2014'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-700/50">
              <span className="text-xs text-slate-500">
                Page {currentPage} of {totalPages}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                  disabled={offset === 0}
                  className="rounded p-1 text-slate-400 hover:bg-slate-800/50 disabled:opacity-30"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setOffset(offset + pageSize)}
                  disabled={offset + pageSize >= total}
                  className="rounded p-1 text-slate-400 hover:bg-slate-800/50 disabled:opacity-30"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}
