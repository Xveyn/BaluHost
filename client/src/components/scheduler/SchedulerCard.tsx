import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Play, Settings, Power, Clock, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import type { SchedulerStatus } from '../../api/schedulers';
import {
  formatRelativeTime,
  getSchedulerIcon,
  getStatusBadgeClasses,
} from '../../api/schedulers';

/**
 * Format interval with i18n support
 */
function formatIntervalTranslated(seconds: number, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (seconds < 60) {
    return seconds === 1 ? t('scheduler:interval.everySecond') : t('scheduler:interval.everySeconds', { count: seconds });
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return minutes === 1 ? t('scheduler:interval.everyMinute') : t('scheduler:interval.everyMinutes', { count: minutes });
  } else if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return hours === 1 ? t('scheduler:interval.everyHour') : t('scheduler:interval.everyHours', { count: hours });
  } else {
    const days = Math.floor(seconds / 86400);
    return days === 1 ? t('scheduler:interval.daily') : t('scheduler:interval.everyDays', { count: days });
  }
}

interface SchedulerCardProps {
  scheduler: SchedulerStatus;
  onRunNow: (name: string) => Promise<void>;
  onConfigure: (scheduler: SchedulerStatus) => void;
  onToggle: (name: string, enabled: boolean) => Promise<void>;
  disabled?: boolean;
}

export function SchedulerCard({
  scheduler,
  onRunNow,
  onConfigure,
  onToggle,
  disabled = false,
}: SchedulerCardProps) {
  const { t } = useTranslation(['scheduler', 'common']);
  const [isRunning, setIsRunning] = useState(false);
  const [isToggling, setIsToggling] = useState(false);

  const handleRunNow = async () => {
    if (isRunning || disabled) return;
    setIsRunning(true);
    try {
      await onRunNow(scheduler.name);
    } finally {
      setIsRunning(false);
    }
  };

  const handleToggle = async () => {
    if (isToggling || disabled) return;
    setIsToggling(true);
    try {
      await onToggle(scheduler.name, !scheduler.is_enabled);
    } finally {
      setIsToggling(false);
    }
  };

  const getStatusIcon = () => {
    if (scheduler.last_status === 'running') {
      return <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />;
    }
    if (scheduler.last_status === 'completed') {
      return <CheckCircle className="h-4 w-4 text-green-400" />;
    }
    if (scheduler.last_status === 'failed') {
      return <AlertCircle className="h-4 w-4 text-red-400" />;
    }
    return null;
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 transition-all hover:border-slate-700">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl" role="img" aria-label={t('scheduler:schedulers.' + scheduler.name + '.name', { defaultValue: scheduler.display_name })}>
            {getSchedulerIcon(scheduler.name)}
          </span>
          <div>
            <h3 className="font-medium text-white">{t('scheduler:schedulers.' + scheduler.name + '.name', { defaultValue: scheduler.display_name })}</h3>
            <p className="text-xs text-slate-400 mt-0.5">{t('scheduler:schedulers.' + scheduler.name + '.description', { defaultValue: scheduler.description })}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {/* Status indicator */}
          {scheduler.is_running && scheduler.is_enabled ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-green-900/50 px-2 py-0.5 text-xs text-green-300">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
              {t('scheduler:card.active')}
            </span>
          ) : !scheduler.is_enabled ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-yellow-900/50 px-2 py-0.5 text-xs text-yellow-300">
              {t('scheduler:card.disabled')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
              {t('scheduler:card.stopped')}
            </span>
          )}
        </div>
      </div>

      {/* Interval info */}
      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <div className="text-xs text-slate-500 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {t('scheduler:card.interval')}
          </div>
          <div className="text-slate-200 mt-0.5">{formatIntervalTranslated(scheduler.interval_seconds, t)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">{t('scheduler:card.nextRun')}</div>
          <div className="text-slate-200 mt-0.5">
            {scheduler.is_enabled && scheduler.next_run_at
              ? formatRelativeTime(scheduler.next_run_at)
              : '-'}
          </div>
        </div>
      </div>

      {/* Last execution */}
      <div className="mt-3 pt-3 border-t border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{t('scheduler:card.last')}:</span>
            {scheduler.last_status ? (
              <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs ${getStatusBadgeClasses(scheduler.last_status)}`}>
                {getStatusIcon()}
                {t('scheduler:status.' + scheduler.last_status)}
              </span>
            ) : (
              <span className="text-xs text-slate-500">{t('scheduler:card.neverRun')}</span>
            )}
          </div>
          {scheduler.last_run_at && (
            <span className="text-xs text-slate-400">
              {formatRelativeTime(scheduler.last_run_at)}
            </span>
          )}
        </div>
        {scheduler.last_error && (
          <div className="mt-2 text-xs text-red-400 bg-red-900/20 rounded px-2 py-1 truncate">
            {scheduler.last_error}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        {scheduler.can_run_manually && (
          <button
            onClick={handleRunNow}
            disabled={disabled || isRunning || !scheduler.is_enabled}
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {t('scheduler:buttons.runNow')}
          </button>
        )}
        <button
          onClick={() => onConfigure(scheduler)}
          disabled={disabled}
          className="inline-flex items-center justify-center rounded-md bg-slate-700 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-600 disabled:opacity-50"
          title={t('scheduler:buttons.configure')}
        >
          <Settings className="h-4 w-4" />
        </button>
        <button
          onClick={handleToggle}
          disabled={disabled || isToggling}
          className={`inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
            scheduler.is_enabled
              ? 'bg-slate-700 text-white hover:bg-slate-600'
              : 'bg-emerald-600 text-white hover:bg-emerald-700'
          }`}
          title={scheduler.is_enabled ? t('scheduler:buttons.disable') : t('scheduler:buttons.enable')}
        >
          {isToggling ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Power className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}
