import { HardDrive, ChevronLeft, ChevronRight } from 'lucide-react';
import { formatBytes } from '../../../lib/formatters';
import type { SSDCacheEntryResponse } from '../../../api/ssd-file-cache';

export function CacheEntriesTable({
  entries,
  entriesTotal,
  page,
  totalPages,
  actionLoading,
  onEvict,
  onPrevPage,
  onNextPage,
}: {
  entries: SSDCacheEntryResponse[];
  entriesTotal: number;
  page: number;
  totalPages: number;
  actionLoading: boolean;
  onEvict: (entryId: number) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
}) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <HardDrive className="w-5 h-5 text-sky-400" />
          Cached Entries
          <span className="text-sm font-normal text-slate-400">({entriesTotal})</span>
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-slate-800">
              <th className="pb-3 text-slate-400 font-medium">Source Path</th>
              <th className="pb-3 text-slate-400 font-medium">Size</th>
              <th className="pb-3 text-slate-400 font-medium">Accesses</th>
              <th className="pb-3 text-slate-400 font-medium">Last Accessed</th>
              <th className="pb-3 text-slate-400 font-medium">Status</th>
              <th className="pb-3 text-slate-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.length > 0 ? entries.map((entry) => (
              <tr key={entry.id} className="border-b border-slate-800/50">
                <td className="py-3 text-slate-300 max-w-xs truncate" title={entry.source_path}>
                  {entry.source_path}
                </td>
                <td className="py-3 text-slate-300">{formatBytes(entry.file_size_bytes)}</td>
                <td className="py-3 text-slate-300">{entry.access_count}</td>
                <td className="py-3 text-slate-300">
                  {new Date(entry.last_accessed).toLocaleString()}
                </td>
                <td className="py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    entry.is_valid
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {entry.is_valid ? 'Valid' : 'Invalid'}
                  </span>
                </td>
                <td className="py-3">
                  <button
                    onClick={() => onEvict(entry.id)}
                    disabled={actionLoading}
                    className="text-red-400 hover:text-red-300 transition-colors disabled:opacity-50 text-xs"
                  >
                    Evict
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500">
                  No cached entries
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-800/60">
          <p className="text-sm text-slate-400">
            Page {page + 1} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={onPrevPage}
              disabled={page === 0}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={onNextPage}
              disabled={page >= totalPages - 1}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
