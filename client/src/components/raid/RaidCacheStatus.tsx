/**
 * SSD cache status row for the RaidArrayCard device table.
 * Renders as a <tr> for desktop and a card for mobile.
 */
import { useState, useEffect } from 'react';
import { Trash2, RotateCw, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import { formatBytes } from '../../lib/formatters';
import { getTypeStyle, getTypeLabel } from './raidUtils';
import {
  getCacheStats,
  updateCacheConfig,
  triggerEviction,
  clearCache,
  type SSDCacheStats,
  type EvictionResult,
} from '../../api/ssd-file-cache';

interface RaidCacheStatusProps {
  arrayName: string;
  busy: boolean;
  onNavigateToCache: (arrayName: string) => void;
}

export default function RaidCacheStatus({ arrayName, busy, onNavigateToCache }: RaidCacheStatusProps) {
  const [stats, setStats] = useState<SSDCacheStats | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const isBusy = busy || actionBusy;

  const reload = () => {
    getCacheStats(arrayName).then(setStats).catch(() => {});
  };

  useEffect(() => {
    reload();
  }, [arrayName]);

  if (!stats) return null;

  const handleToggle = async () => {
    setActionBusy(true);
    try {
      await updateCacheConfig(arrayName, { is_enabled: !stats.is_enabled });
      toast.success(stats.is_enabled ? 'SSD Cache disabled' : 'SSD Cache enabled');
      reload();
    } catch {
      toast.error('Failed to toggle SSD Cache');
    } finally {
      setActionBusy(false);
    }
  };

  const handleEviction = async () => {
    setActionBusy(true);
    try {
      const result: EvictionResult = await triggerEviction(arrayName);
      toast.success(`Eviction complete: ${result.deleted_count} entries freed (${formatBytes(result.freed_bytes)})`);
      reload();
    } catch {
      toast.error('Eviction failed');
    } finally {
      setActionBusy(false);
    }
  };

  const handleClear = async () => {
    if (!window.confirm('Clear all cached files? This cannot be undone.')) return;
    setActionBusy(true);
    try {
      const result: EvictionResult = await clearCache(arrayName);
      toast.success(`Cache cleared: ${result.deleted_count} entries removed (${formatBytes(result.freed_bytes)})`);
      reload();
    } catch {
      toast.error('Failed to clear cache');
    } finally {
      setActionBusy(false);
    }
  };

  const hasHitData = stats.total_hits + stats.total_misses > 0;

  const statusBadgeClass = stats.is_enabled
    ? 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200'
    : 'border-slate-700/60 bg-slate-900/60 text-slate-300';

  // Shared button base
  const btnDisabled = 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500';

  return (
    <>
      {/* Desktop table row */}
      <tr className="group transition hover:bg-slate-900/65 hidden lg:table-row">
        <td className="px-5 py-4">
          <span className="text-sm font-medium text-slate-200">SSD Cache</span>
          {stats.is_enabled && (
            <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
              <span>{formatBytes(stats.current_size_bytes)} / {formatBytes(stats.max_size_bytes)}</span>
              {hasHitData && (
                <>
                  <span>·</span>
                  <span>Hit Rate: {stats.hit_rate_percent.toFixed(1)}%</span>
                </>
              )}
            </div>
          )}
        </td>
        <td className="px-5 py-4">
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${statusBadgeClass}`}>
            {stats.is_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </td>
        <td className="px-5 py-4">
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${getTypeStyle('cache')}`}>
            {getTypeLabel('cache')}
          </span>
        </td>
        <td className="px-5 py-4 text-sm">
          <div className="flex gap-2">
            <button
              onClick={handleToggle}
              disabled={isBusy}
              className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                isBusy
                  ? btnDisabled
                  : stats.is_enabled
                    ? 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60'
                    : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100 hover:border-emerald-500/60'
              }`}
            >
              {stats.is_enabled ? 'Disable' : 'Enable'}
            </button>
            {stats.is_enabled && (
              <>
                <button
                  onClick={handleEviction}
                  disabled={isBusy}
                  className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                    isBusy
                      ? btnDisabled
                      : 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60'
                  }`}
                  title="Trigger eviction cycle"
                >
                  <span className="flex items-center gap-1"><RotateCw className="h-3 w-3" /> Eviction</span>
                </button>
                <button
                  onClick={handleClear}
                  disabled={isBusy}
                  className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                    isBusy
                      ? btnDisabled
                      : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                  }`}
                  title="Clear all cached files"
                >
                  <span className="flex items-center gap-1"><Trash2 className="h-3 w-3" /> Clear</span>
                </button>
              </>
            )}
            <button
              onClick={() => onNavigateToCache(arrayName)}
              className="whitespace-nowrap rounded-lg border border-slate-700/70 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-200 transition touch-manipulation active:scale-95 hover:border-slate-600"
              title="Open full SSD Cache settings"
            >
              <span className="flex items-center gap-1">Details <ExternalLink className="h-3 w-3" /></span>
            </button>
          </div>
        </td>
      </tr>

      {/* Mobile card */}
      <div className="lg:hidden rounded-xl border border-slate-800/60 bg-slate-900/60 p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-200">SSD Cache</span>
          <div className="flex items-center gap-1.5">
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusBadgeClass}`}>
              {stats.is_enabled ? 'Enabled' : 'Disabled'}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getTypeStyle('cache')}`}>
              {getTypeLabel('cache')}
            </span>
          </div>
        </div>
        {stats.is_enabled && (
          <p className="mt-1.5 text-xs text-slate-500">
            {formatBytes(stats.current_size_bytes)} / {formatBytes(stats.max_size_bytes)}
            {hasHitData && ` · Hit Rate: ${stats.hit_rate_percent.toFixed(1)}%`}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            onClick={handleToggle}
            disabled={isBusy}
            className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
              isBusy
                ? btnDisabled
                : stats.is_enabled
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                  : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
            }`}
          >
            {stats.is_enabled ? 'Disable' : 'Enable'}
          </button>
          {stats.is_enabled && (
            <>
              <button
                onClick={handleEviction}
                disabled={isBusy}
                className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                  isBusy ? btnDisabled : 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                }`}
              >
                Eviction
              </button>
              <button
                onClick={handleClear}
                disabled={isBusy}
                className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                  isBusy ? btnDisabled : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                }`}
              >
                Clear
              </button>
            </>
          )}
          <button
            onClick={() => onNavigateToCache(arrayName)}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-2 py-1 text-[10px] text-slate-200 transition touch-manipulation active:scale-95"
          >
            Details
          </button>
        </div>
      </div>
    </>
  );
}
