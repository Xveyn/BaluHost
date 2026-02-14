import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2 } from 'lucide-react';
import type { SchedulerStatus, SchedulerConfigUpdate } from '../../api/schedulers';

interface SchedulerConfigModalProps {
  scheduler: SchedulerStatus | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (name: string, config: SchedulerConfigUpdate) => Promise<boolean>;
}

type IntervalUnit = 'seconds' | 'minutes' | 'hours' | 'days';

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
    }
  }, [scheduler]);

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

      // Validate minimum interval (60 seconds)
      if (intervalSeconds < 60) {
        setError(t('scheduler:configModal.minIntervalError'));
        setIsSaving(false);
        return;
      }

      const config: SchedulerConfigUpdate = {
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
    } catch (err: any) {
      setError(err.message || t('scheduler:configModal.saveFailed'));
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

          {/* Interval */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              {t('scheduler:configModal.runInterval')}
            </label>
            <div className="flex gap-2">
              <input
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
