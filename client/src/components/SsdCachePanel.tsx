import { useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { Zap } from 'lucide-react';
import {
  configureCache,
  detachCache,
  type CacheMode,
  type CacheStatus,
} from '../api/ssd-cache';
import { formatBytes } from '../lib/formatters';
import { useConfirmDialog } from '../hooks/useConfirmDialog';

interface SsdCachePanelProps {
  cache: CacheStatus;
  onRefresh: () => Promise<void>;
  onSetupCache?: () => void;
}

const modeStyles: Record<string, string> = {
  writethrough: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  writeback: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  writearound: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  none: 'border-slate-700/50 bg-slate-800/40 text-slate-400',
};

const stateStyles: Record<string, string> = {
  running: 'text-emerald-400',
  detaching: 'text-amber-400',
  error: 'text-rose-400',
  idle: 'text-slate-400',
};

export default function SsdCachePanel({ cache, onRefresh }: SsdCachePanelProps) {
  const { t } = useTranslation(['system']);
  const { confirm, dialog } = useConfirmDialog();
  const [busy, setBusy] = useState(false);
  const [showModeSelect, setShowModeSelect] = useState(false);

  const handleChangeMode = async (newMode: CacheMode) => {
    setBusy(true);
    try {
      const response = await configureCache({ array: cache.array_name, mode: newMode });
      toast.success(response.message);
      setShowModeSelect(false);
      await onRefresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('system:raid.cache.messages.configureFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleDetach = async () => {
    const ok = await confirm(
      t('system:raid.cache.messages.detachConfirm', { array: cache.array_name }),
      {
        title: t('system:raid.cache.actions.detach'),
        variant: 'danger',
        confirmLabel: t('system:raid.cache.actions.detach'),
      },
    );
    if (!ok) return;

    setBusy(true);
    try {
      const response = await detachCache({ array: cache.array_name });
      toast.success(response.message);
      await onRefresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('system:raid.cache.messages.detachFailed'));
    } finally {
      setBusy(false);
    }
  };

  const usagePercent = cache.cache_size_bytes > 0
    ? Math.round((cache.cache_used_bytes / cache.cache_size_bytes) * 100)
    : 0;

  return (
    <div className="border-t border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="space-y-2 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-teal-600 shadow-lg shadow-cyan-500/20">
              <Zap className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-xs sm:text-sm font-medium text-white">
              {t('system:raid.cache.title')}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] sm:text-xs font-medium ${modeStyles[cache.mode] ?? modeStyles.none}`}>
              {cache.mode}
            </span>
            <span className={`text-[10px] sm:text-xs ${stateStyles[cache.state] ?? stateStyles.idle}`}>
              {cache.state}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-xs text-slate-400">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">
                {t('system:raid.cache.labels.device')}
              </span>
              <p className="text-slate-300">{cache.cache_device}</p>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">
                {t('system:raid.cache.labels.hitRate')}
              </span>
              <p className="text-slate-300">
                {cache.hit_rate_percent !== null ? `${cache.hit_rate_percent}%` : '—'}
              </p>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">
                {t('system:raid.cache.labels.usage')}
              </span>
              <p className="text-slate-300">
                {formatBytes(cache.cache_used_bytes)} / {formatBytes(cache.cache_size_bytes)}
                {cache.cache_size_bytes > 0 && ` (${usagePercent}%)`}
              </p>
            </div>
            {cache.mode === 'writeback' && cache.dirty_data_bytes > 0 && (
              <div>
                <span className="text-[10px] uppercase tracking-wider text-amber-500">
                  {t('system:raid.cache.labels.dirtyData')}
                </span>
                <p className="text-amber-300">{formatBytes(cache.dirty_data_bytes)}</p>
              </div>
            )}
          </div>

          {/* Usage bar */}
          {cache.cache_size_bytes > 0 && (
            <div className="h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-teal-500"
                style={{ width: `${Math.min(usagePercent, 100)}%` }}
              />
            </div>
          )}
        </div>

        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={() => setShowModeSelect(!showModeSelect)}
            disabled={busy}
            className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
              busy
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-cyan-500/40'
            }`}
          >
            {t('system:raid.cache.actions.changeMode')}
          </button>
          <button
            onClick={handleDetach}
            disabled={busy}
            className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
              busy
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
            }`}
          >
            {t('system:raid.cache.actions.detach')}
          </button>
        </div>
      </div>

      {/* Mode selector dropdown */}
      {showModeSelect && (
        <div className="mt-3 flex flex-wrap gap-2">
          {(['writethrough', 'writeback', 'writearound'] as CacheMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => handleChangeMode(mode)}
              disabled={busy || mode === cache.mode}
              className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                mode === cache.mode
                  ? 'border-cyan-500/40 bg-cyan-500/15 text-cyan-100'
                  : busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'
              }`}
            >
              {mode}
              {mode === 'writethrough' && ` (${t('system:raid.cache.labels.safe')})`}
              {mode === 'writeback' && ` (${t('system:raid.cache.labels.fast')})`}
            </button>
          ))}
        </div>
      )}

      {dialog}
    </div>
  );
}
