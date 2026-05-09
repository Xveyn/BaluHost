/**
 * Always-Awake panel.
 *
 * Master toggle + optional expiry presets (1h/4h/8h/permanent) plus a
 * custom datetime picker capped at 7 days.
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

type Preset = '1h' | '4h' | '8h' | 'permanent' | 'custom';

const PRESET_HOURS: Record<Exclude<Preset, 'permanent' | 'custom'>, number> = {
  '1h': 1,
  '4h': 4,
  '8h': 8,
};

const MIN_HORIZON_MS = 5 * 60 * 1000;        // 5 minutes
const MAX_HORIZON_MS = 7 * 24 * 3600 * 1000; // 7 days

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  // Within the next 7 days: "DD.MM. HH:mm". Beyond (shouldn't happen with the cap)
  // we still render the full date.
  const ddmm = d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
  const hhmm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${ddmm} ${hhmm}`;
}

function formatRemaining(seconds: number): string {
  if (seconds < 0) return '0m';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/** Convert a Date into the value format expected by <input type="datetime-local"> in the user's local TZ. */
function toLocalInputValue(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
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
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerValue, setPickerValue] = useState<string>('');
  const [pickerError, setPickerError] = useState<string | null>(null);
  const tickRef = useRef<number | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [cfg, status] = await Promise.all([getSleepConfig(), getSleepStatus()]);
      setEnabled(cfg.always_awake_enabled ?? false);
      setUntil(cfg.always_awake_until ?? null);
      setExpiresIn(status.always_awake?.expires_in_seconds ?? null);
      setScheduleEnabled(cfg.schedule_enabled);
      setCoreUptimeEnabled(cfg.core_uptime_enabled ?? false);

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
        let best: Preset | null = null;
        let bestDiff = 5 * 60;
        for (const [p, sec] of candidates) {
          const diff = Math.abs(remaining - sec);
          if (diff <= bestDiff) {
            bestDiff = diff;
            best = p;
          }
        }
        setActivePreset(best ?? 'custom');
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

  useEffect(() => {
    if (expiresIn === 0) {
      setExpiresIn(null);
      refresh();
    }
  }, [expiresIn, refresh]);

  // Close popover on outside click / Escape.
  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPickerOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen]);

  const setPreset = async (preset: Exclude<Preset, 'custom'>) => {
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

  const setCustomPreset = async (localValue: string) => {
    const target = new Date(localValue);
    if (Number.isNaN(target.getTime())) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorPast'));
      return;
    }
    const delta = target.getTime() - Date.now();
    if (delta < MIN_HORIZON_MS) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorPast'));
      return;
    }
    if (delta > MAX_HORIZON_MS) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorMax'));
      return;
    }

    const newUntil = target.toISOString();
    const previousEnabled = enabled;
    const previousUntil = until;
    const previousExpiresIn = expiresIn;
    const previousActivePreset = activePreset;
    setEnabled(true);
    setUntil(newUntil);
    setExpiresIn(Math.floor(delta / 1000));
    setActivePreset('custom');
    setPickerOpen(false);
    setPickerError(null);
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

  const openPicker = () => {
    const seed =
      activePreset === 'custom' && until
        ? new Date(until)
        : new Date(Date.now() + 4 * 3600 * 1000); // default seed: now+4h
    setPickerValue(toLocalInputValue(seed));
    setPickerError(null);
    setPickerOpen(true);
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

  const minLocal = toLocalInputValue(new Date(Date.now() + MIN_HORIZON_MS));
  const maxLocal = toLocalInputValue(new Date(Date.now() + MAX_HORIZON_MS));

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
        {(['1h', '4h', '8h', 'permanent'] as const).map((p) => {
          const isActive = enabled && activePreset === p;
          const labelKey =
            p === 'permanent'
              ? 'sleep.alwaysAwake.presetPermanent'
              : (`sleep.alwaysAwake.preset${p}` as const);
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

        <div className="relative" ref={pickerRef}>
          <button
            type="button"
            onClick={openPicker}
            className={`min-w-[3.5rem] rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              enabled && activePreset === 'custom'
                ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50'
                : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
            }`}
          >
            {enabled && activePreset === 'custom' && until
              ? t('sleep.alwaysAwake.activeCustom', { datetime: formatDateTime(until) })
              : t('sleep.alwaysAwake.presetCustom')}
          </button>

          {pickerOpen && (
            <div className="absolute z-10 mt-2 right-0 sm:right-auto sm:left-0 w-72 rounded-md border border-slate-700/60 bg-slate-900 p-3 shadow-xl space-y-2">
              <label className="block text-xs text-slate-300">
                {t('sleep.alwaysAwake.pickerLabel')}
                <input
                  type="datetime-local"
                  className="mt-1 block w-full rounded border border-slate-700/60 bg-slate-800 px-2 py-1 text-sm text-slate-100"
                  min={minLocal}
                  max={maxLocal}
                  value={pickerValue}
                  onChange={(e) => {
                    setPickerValue(e.target.value);
                    setPickerError(null);
                  }}
                />
              </label>
              {pickerError && (
                <p className="text-xs text-red-400">{pickerError}</p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setPickerOpen(false)}
                  className="rounded px-2 py-1 text-xs text-slate-400 hover:text-slate-200"
                >
                  {t('sleep.alwaysAwake.pickerCancel')}
                </button>
                <button
                  type="button"
                  onClick={() => setCustomPreset(pickerValue)}
                  className="rounded px-2 py-1 text-xs font-medium bg-amber-500/30 text-amber-200 border border-amber-500/50 hover:bg-amber-500/40"
                >
                  {t('sleep.alwaysAwake.pickerApply')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
