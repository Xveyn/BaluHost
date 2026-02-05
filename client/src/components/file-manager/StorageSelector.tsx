/**
 * StorageSelector component -- renders the storage drive selector bar.
 */

import { formatBytes } from '../../lib/formatters';
import type { StorageMountpoint } from './types';

interface StorageSelectorProps {
  mountpoints: StorageMountpoint[];
  selectedMountpoint: StorageMountpoint | null;
  onSelect: (mp: StorageMountpoint) => void;
}

export function StorageSelector({ mountpoints, selectedMountpoint, onSelect }: StorageSelectorProps) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] sm:tracking-[0.25em] text-slate-500">Storage:</span>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {mountpoints.map((mp) => (
            <button
              key={mp.id}
              onClick={() => onSelect(mp)}
              className={`flex items-center gap-2 rounded-xl border px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition touch-manipulation active:scale-95 ${
                selectedMountpoint?.id === mp.id
                  ? 'border-sky-500/50 bg-sky-500/10 text-sky-200'
                  : 'border-slate-700/70 bg-slate-950/70 text-slate-300 hover:border-sky-500/40 hover:text-white'
              }`}
            >
              <span className="text-sm sm:text-base">
                {mp.type === 'raid' ? '💾' : mp.type === 'dev-storage' ? '🔧' : '💿'}
              </span>
              <div className="flex flex-col items-start">
                <span className="font-semibold truncate max-w-[120px] sm:max-w-none">{mp.name}</span>
                <span className="text-[10px] sm:text-xs text-slate-400">
                  {formatBytes(mp.used_bytes)} / {formatBytes(mp.size_bytes)}
                  {mp.raid_level && <span className="hidden sm:inline"> • {mp.raid_level.toUpperCase()}</span>}
                  {mp.status !== 'optimal' && (
                    <span className="ml-1 text-amber-400">⚠</span>
                  )}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
