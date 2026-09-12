import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2 } from 'lucide-react';
import type { SchedulerStatus, SchedulerConfigUpdate, RebootPreview } from '../../api/schedulers';
import { getRebootPreview } from '../../api/schedulers';

interface SchedulerConfigModalProps {
  scheduler: SchedulerStatus | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (name: string, config: SchedulerConfigUpdate) => Promise<boolean>;
}

type IntervalUnit = 'seconds' | 'minutes' | 'hours' | 'days';

/** Reine Uhrzeit, keine Relativangabe - fuer den Kernbetriebszeit-Warntext. */
function formatTime(iso: string | null): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function SchedulerConfigModal({
  scheduler,
  isOpen,
  onClose,
  onSave,
}: SchedulerConfigModalProps) {
  const { t } = useTranslation(['scheduler', 'common']);
  const [intervalValue, setIntervalValue] = useState(1);
  const [intervalUnit, setIntervalUnit] = useState<IntervalUnit>('hours');
  const [isEnabled, setIsEnabled] = useState(true);
  const [backupType, setBackupType] = useState('full');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isReboot = scheduler?.name === 'system_reboot';
  const [weekday, setWeekday] = useState(6);
  const [time, setTime] = useState('04:00');
  const [retryHours, setRetryHours] = useState(6);
  const [leadMinutes, setLeadMinutes] = useState(10);
  const [preview, setPreview] = useState<RebootPreview | null>(null);

  // Initialize form when scheduler changes
  useEffect(() => {
    if (scheduler) {
      const seconds = scheduler.interval_seconds;
      setIsEnabled(scheduler.is_enabled);
      setError(null);

      // Convert seconds to appropriate unit
      if (seconds >= 86400 && seconds % 86400 === 0) {
        setIntervalValue(seconds / 86400);
        setIntervalUnit('days');
      } else if (seconds >= 3600 && seconds % 3600 === 0) {
        setIntervalValue(seconds / 3600);
        setIntervalUnit('hours');
      } else if (seconds >= 60 && seconds % 60 === 0) {
        setIntervalValue(seconds / 60);
        setIntervalUnit('minutes');
      } else {
        setIntervalValue(seconds);
        setIntervalUnit('seconds');
      }

      // Initialize backup type from extra_config
      if (scheduler.name === 'backup' && scheduler.extra_config?.backup_type) {
        setBackupType(scheduler.extra_config.backup_type);
      } else {
        setBackupType('full');
      }

      // Initialize weekday/time/retry/lead from extra_config (system_reboot)
      if (scheduler.name === 'system_reboot') {
        const extra = scheduler.extra_config ?? {};
        setWeekday(Number(extra.weekday ?? 6));
        setTime(String(extra.time ?? '04:00'));
        setRetryHours(Number(extra.retry_window_hours ?? 6));
        setLeadMinutes(Number(extra.warning_lead_minutes ?? 10));
      }
    }
  }, [scheduler]);

  // Load the server-computed collision preview for system_reboot. The
  // collision rule lives once, in the backend automaton (spec section 8);
  // duplicating it client-side would drift. This is why the preview reflects
  // the *saved* schedule, not whatever is currently being typed - it reloads
  // after a successful save.
  useEffect(() => {
    if (!isOpen || !isReboot) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    getRebootPreview()
      .then((value) => { if (!cancelled) setPreview(value); })
      .catch(() => { if (!cancelled) setPreview(null); });
    return () => { cancelled = true; };
  }, [isOpen, isReboot, weekday, time, retryHours]);

  const handleSave = async () => {
    if (!scheduler) return;

    setIsSaving(true);
    setError(null);

    try {
      // Convert interval to seconds
      let intervalSeconds = intervalValue;
      switch (intervalUnit) {
        case 'minutes':
          intervalSeconds = intervalValue * 60;
          break;
        case 'hours':
          intervalSeconds = intervalValue * 3600;
          break;
        case 'days':
          intervalSeconds = intervalValue * 86400;
          break;
      }

      // Validate minimum interval (60 seconds) - system_reboot has no interval
      if (!isReboot && intervalSeconds < 60) {
        setError(t('scheduler:configModal.minIntervalError'));
        setIsSaving(false);
        return;
      }

      const config: SchedulerConfigUpdate = isReboot
        ? {
            is_enabled: isEnabled,
            extra_config: {
              weekday,
              time,
              retry_window_hours: retryHours,
              warning_lead_minutes: leadMinutes,
            },
          }
        : {
            interval_seconds: intervalSeconds,
            is_enabled: isEnabled,
            ...(scheduler.name === 'backup' && {
              extra_config: { backup_type: backupType },
            }),
          };

      const success = await onSave(scheduler.name, config);
      if (success) {
        onClose();
      } else {
        setError(t('scheduler:configModal.saveFailed'));
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('scheduler:configModal.saveFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen || !scheduler) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className="relative z-10 w-full max-w-[95vw] sm:max-w-md max-h-[90vh] overflow-y-auto rounded-lg bg-slate-900 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="config-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h3 id="config-modal-title" className="text-lg font-medium text-white">
            {t('scheduler:configModal.title', { name: t('scheduler:schedulers.' + scheduler.name + '.name', { defaultValue: scheduler.display_name }) })}
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4 space-y-4">
          {/* Info */}
          <p className="text-sm text-slate-400">{t('scheduler:schedulers.' + scheduler.name + '.description', { defaultValue: scheduler.description })}</p>

          {/* Interval (not applicable to system_reboot, which has no interval) */}
          {!isReboot && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                {t('scheduler:configModal.runInterval')}
              </label>
              <div className="flex gap-2">
                <input
                  data-testid="interval-value"
                  type="number"
                  min="1"
                  value={intervalValue}
                  onChange={(e) => setIntervalValue(Math.max(1, parseInt(e.target.value) || 1))}
                  className="flex-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                />
                <select
                  value={intervalUnit}
                  onChange={(e) => setIntervalUnit(e.target.value as IntervalUnit)}
                  className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                >
                  <option value="seconds">{t('scheduler:configModal.units.seconds')}</option>
                  <option value="minutes">{t('scheduler:configModal.units.minutes')}</option>
                  <option value="hours">{t('scheduler:configModal.units.hours')}</option>
                  <option value="days">{t('scheduler:configModal.units.days')}</option>
                </select>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {t('scheduler:configModal.minIntervalHint')}
              </p>
            </div>
          )}

          {/* Weekday/time (system_reboot only, in place of the interval controls) */}
          {isReboot && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('scheduler:configModal.reboot.weekday')}
                </label>
                <select
                  data-testid="reboot-weekday"
                  value={weekday}
                  onChange={(e) => setWeekday(Number(e.target.value))}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                >
                  {[0, 1, 2, 3, 4, 5, 6].map((day) => (
                    <option key={day} value={day}>{t(`scheduler:weekdays.${day}`)}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('scheduler:configModal.reboot.time')}
                </label>
                <input
                  data-testid="reboot-time"
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('scheduler:configModal.reboot.retryHours')}
                </label>
                <input
                  data-testid="reboot-retry"
                  type="number"
                  min={1}
                  max={24}
                  value={retryHours}
                  onChange={(e) => setRetryHours(Number(e.target.value))}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('scheduler:configModal.reboot.leadMinutes')}
                </label>
                <input
                  data-testid="reboot-lead"
                  type="number"
                  min={0}
                  max={120}
                  value={leadMinutes}
                  onChange={(e) => setLeadMinutes(Number(e.target.value))}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
                />
              </div>

              {/* Core-uptime collision warning - not blocking, the window can be changed later */}
              {preview?.in_core_uptime && (
                <div
                  data-testid="reboot-core-uptime-warning"
                  className="rounded-md bg-amber-900/30 border border-amber-800 px-3 py-2 text-sm text-amber-300"
                >
                  {preview.reachable
                    ? t('scheduler:configModal.reboot.warningDeferred', {
                        window: preview.window_label ?? '',
                        windowEnds: formatTime(preview.window_ends_at),
                      })
                    : t('scheduler:configModal.reboot.warningNever', {
                        window: preview.window_label ?? '',
                        windowEnds: formatTime(preview.window_ends_at),
                        retryHours,
                      })}
                </div>
              )}
            </div>
          )}

          {/* Backup Type (only for backup scheduler) */}
          {scheduler.name === 'backup' && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                {t('scheduler:configModal.backupType')}
              </label>
              <select
                value={backupType}
                onChange={(e) => setBackupType(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none"
              >
                <option value="full">{t('scheduler:configModal.backupTypes.full')}</option>
                <option value="database_only">{t('scheduler:configModal.backupTypes.database_only')}</option>
                <option value="files_only">{t('scheduler:configModal.backupTypes.files_only')}</option>
                <option value="incremental">{t('scheduler:configModal.backupTypes.incremental')}</option>
              </select>
            </div>
          )}

          {/* Enabled toggle */}
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-slate-300">
              {t('scheduler:configModal.enabled')}
            </label>
            <button
              type="button"
              role="switch"
              aria-checked={isEnabled}
              onClick={() => setIsEnabled(!isEnabled)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                isEnabled ? 'bg-emerald-600' : 'bg-slate-700'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  isEnabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {/* Config key info */}
          {scheduler.config_key && (
            <div className="rounded-md bg-slate-800/50 p-3">
              <p className="text-xs text-slate-400">
                {t('scheduler:configModal.envVar')}: <code className="text-slate-300">{scheduler.config_key}</code>
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {t('scheduler:configModal.envVarNote')}
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-md bg-red-900/30 border border-red-800 px-3 py-2">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 transition-colors"
          >
            {t('common:buttons.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {t('common:buttons.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
