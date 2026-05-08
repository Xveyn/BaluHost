/**
 * Always-Awake panel.
 *
 * Master toggle + optional expiry presets (1h/4h/8h/permanent).
 * Auto-saves all changes; manual Sleep/Suspend on the server side
 * automatically clears the override.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Coffee, Clock, X } from 'lucide-react';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
} from '../../api/sleep';

type Preset = '1h' | '4h' | '8h' | 'permanent';

const PRESET_HOURS: Record<Exclude<Preset, 'permanent'>, number> = {
  '1h': 1,
  '4h': 4,
  '8h': 8,
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatRemaining(seconds: number): string {
  if (seconds < 0) return '0m';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function AlwaysAwakePanel() {
  const { t } = useTranslation('system');
  const [enabled, setEnabled] = useState(false);
  const [until, setUntil] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [coreUptimeEnabled, setCoreUptimeEnabled] = useState(false);
  const [activePreset, setActivePreset] = useState<Preset | null>(null);
  const [loading, setLoading] = useState(true);
  const tickRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [cfg, status] = await Promise.all([getSleepConfig(), getSleepStatus()]);
      setEnabled(cfg.always_awake_enabled ?? false);
      setUntil(cfg.always_awake_until ?? null);
      setExpiresIn(status.always_awake?.expires_in_seconds ?? null);
      setScheduleEnabled(cfg.schedule_enabled);
      setCoreUptimeEnabled(cfg.core_uptime_enabled ?? false);

      // Infer active preset from loaded state (e.g. after page refresh)
      if (!cfg.always_awake_enabled) {
        setActivePreset(null);
      } else if (cfg.always_awake_until == null) {
        setActivePreset('permanent');
      } else {
        const remaining = status.always_awake?.expires_in_seconds ?? 0;
        const candidates: Array<[Preset, number]> = [
          ['1h', 1 * 3600],
          ['4h', 4 * 3600],
          ['8h', 8 * 3600],
        ];
        // Pick the closest preset within 5 minutes; otherwise null (custom).
        let best: Preset | null = null;
        let bestDiff = 5 * 60;
        for (const [p, sec] of candidates) {
          const diff = Math.abs(remaining - sec);
          if (diff <= bestDiff) {
            bestDiff = diff;
            best = p;
          }
        }
        setActivePreset(best);
      }
    } catch {
      toast.error(t('sleep.alwaysAwake.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Live countdown — decrement every second when until is set
  useEffect(() => {
    if (expiresIn === null) {
      if (tickRef.current) window.clearInterval(tickRef.current);
      return;
    }
    tickRef.current = window.setInterval(() => {
      setExpiresIn((prev) => (prev === null ? null : Math.max(0, prev - 1)));
    }, 1000);
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current);
    };
  }, [expiresIn !== null]);

  // Auto-refresh when expired — null out expiresIn first so the countdown effect's
  // cleanup runs immediately even if the refresh request is slow/fails.
  useEffect(() => {
    if (expiresIn === 0) {
      setExpiresIn(null);
      refresh();
    }
  }, [expiresIn, refresh]);

  const setPreset = async (preset: Preset) => {
    const newUntil =
      preset === 'permanent'
        ? null
        : new Date(Date.now() + PRESET_HOURS[preset] * 3600 * 1000).toISOString();
    const previousEnabled = enabled;
    const previousUntil = until;
    const previousExpiresIn = expiresIn;
    const previousActivePreset = activePreset;
    setEnabled(true);
    setUntil(newUntil);
    setExpiresIn(newUntil ? PRESET_HOURS[preset as keyof typeof PRESET_HOURS] * 3600 : null);
    setActivePreset(preset);
    try {
      await updateSleepConfig({
        always_awake_enabled: true,
        always_awake_until: newUntil,
      });
    } catch (err) {
      setEnabled(previousEnabled);
      setUntil(previousUntil);
      setExpiresIn(previousExpiresIn);
      setActivePreset(previousActivePreset);
      toast.error(err instanceof Error ? err.message : t('sleep.alwaysAwake.saveFailed'));
    }
  };

  const handleCancel = async () => {
    const prev = { enabled, until, expiresIn, activePreset };
    setEnabled(false);
    setUntil(null);
    setExpiresIn(null);
    setActivePreset(null);
    try {
      await updateSleepConfig({ always_awake_enabled: false });
    } catch (err) {
      setEnabled(prev.enabled);
      setUntil(prev.until);
      setExpiresIn(prev.expiresIn);
      setActivePreset(prev.activePreset);
      toast.error(err instanceof Error ? err.message : t('sleep.alwaysAwake.saveFailed'));
    }
  };

  const handleMasterToggle = async () => {
    if (enabled) {
      await handleCancel();
    } else {
      await setPreset('permanent');
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-24 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Coffee className="h-4 w-4 text-amber-400" />
          <div>
            <h4 className="text-sm font-medium text-white">{t('sleep.alwaysAwake.title')}</h4>
            <p className="mt-0.5 text-xs text-slate-400">{t('sleep.alwaysAwake.description')}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleMasterToggle}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
            enabled ? 'bg-amber-500' : 'bg-slate-600'
          }`}
          aria-label={t('sleep.alwaysAwake.masterToggle')}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
              enabled ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
      </div>

      {enabled && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-amber-200">
            <Clock className="h-4 w-4 shrink-0" />
            {until && expiresIn !== null ? (
              <span>{t('sleep.alwaysAwake.activeUntil', {
                time: formatTime(until),
                remaining: formatRemaining(expiresIn),
              })}</span>
            ) : (
              <span>{t('sleep.alwaysAwake.activePermanent')}</span>
            )}
            <button
              type="button"
              onClick={handleCancel}
              className="ml-auto inline-flex items-center gap-1 rounded px-2 py-0.5 text-slate-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              {t('sleep.alwaysAwake.cancel')}
            </button>
          </div>

          {(scheduleEnabled || coreUptimeEnabled) && until && (
            <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.alwaysAwake.hintScheduleResumes', { time: formatTime(until) })}
            </div>
          )}
          {(scheduleEnabled || coreUptimeEnabled) && !until && (
            <div className="rounded border border-blue-500/20 bg-blue-500/10 p-2 text-xs text-blue-300">
              {t('sleep.alwaysAwake.hintPermanentClearToResume')}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {(['1h', '4h', '8h', 'permanent'] as Preset[]).map((p) => {
          const isActive = enabled && activePreset === p;
          const labelKey =
            p === 'permanent'
              ? 'sleep.alwaysAwake.presetPermanent'
              : `sleep.alwaysAwake.preset${p}` as const;
          return (
            <button
              key={p}
              type="button"
              onClick={() => setPreset(p)}
              className={`min-w-[3.5rem] rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50'
                  : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
              }`}
            >
              {t(labelKey)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
