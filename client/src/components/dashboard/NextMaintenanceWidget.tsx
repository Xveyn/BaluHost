/**
 * Next Maintenance Widget for Dashboard
 * Shows next scheduled maintenance task
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useNextMaintenance, formatNextRun, formatScheduleWindow } from '../../hooks/useNextMaintenance';
import { getSchedulerIcon } from '../../api/schedulers';
import { Clock, Calendar, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { formatNumber } from '../../lib/formatters';

interface NextMaintenanceWidgetProps {
  showAllSchedulers?: boolean;
}

export const NextMaintenanceWidget: React.FC<NextMaintenanceWidgetProps> = ({
  showAllSchedulers = false,
}) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const { nextMaintenance, allSchedulers, loading, error } = useNextMaintenance();

  const handleViewPlan = () => {
    navigate('/schedulers');
  };

  // Get status icon for last run
  const getStatusIcon = (status: string | null) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
      case 'failed':
        return <XCircle className="h-3.5 w-3.5 text-rose-400" />;
      case 'running':
        return <Clock className="h-3.5 w-3.5 text-sky-400 animate-pulse" />;
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-800/50 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{t('dashboard:maintenance.title')}</p>
        <div className="mt-2 h-6 w-48 rounded bg-slate-800 animate-pulse" />
        <div className="mt-3 h-4 w-64 rounded bg-slate-800/50 animate-pulse" />
        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3">
          <div className="h-4 w-32 rounded bg-slate-800/50 animate-pulse" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card border-slate-800/50 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{t('dashboard:maintenance.title')}</p>
        <h3 className="mt-2 text-lg font-semibold text-slate-400">{t('dashboard:maintenance.unableToLoad')}</h3>
        <p className="mt-3 text-sm text-rose-300">{error}</p>
      </div>
    );
  }

  if (!nextMaintenance) {
    return (
      <div className="card border-slate-800/50 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{t('dashboard:maintenance.title')}</p>
        <h3 className="mt-2 text-lg font-semibold text-slate-400">{t('dashboard:maintenance.noScheduledTasks')}</h3>
        <p className="mt-3 text-sm text-slate-500">{t('dashboard:maintenance.allDisabled')}</p>
        <div className="mt-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-slate-500" />
            <span className="text-slate-400">{t('dashboard:maintenance.configureSchedulers')}</span>
          </div>
          <button
            onClick={handleViewPlan}
            className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white"
          >
            {t('dashboard:maintenance.manage')}
          </button>
        </div>
      </div>
    );
  }

  const { scheduler, nextRunAt, isOverdue } = nextMaintenance;
  const icon = getSchedulerIcon(scheduler.name);

  return (
    <div className="card border-slate-800/50 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{t('dashboard:maintenance.title')}</p>
          <h3 className="mt-2 text-lg font-semibold text-white flex items-center gap-2">
            <span>{icon}</span>
            {scheduler.display_name}
          </h3>
        </div>
        {isOverdue && (
          <div className="flex items-center gap-1 rounded-full bg-amber-500/20 px-2 py-0.5">
            <AlertTriangle className="h-3 w-3 text-amber-400" />
            <span className="text-xs text-amber-300">{t('dashboard:maintenance.overdue')}</span>
          </div>
        )}
      </div>

      <p className="mt-3 text-sm text-slate-400">{scheduler.description}</p>

      {scheduler.last_status && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
          {getStatusIcon(scheduler.last_status)}
          <span>
            Last run: {scheduler.last_status}
            {scheduler.last_duration_ms && ` (${formatNumber(scheduler.last_duration_ms / 1000, 1)}s)`}
          </span>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('dashboard:maintenance.window')}</p>
          <p className="mt-1 text-sm text-slate-200">{formatScheduleWindow(nextRunAt)}</p>
          <p className="text-xs text-slate-500 mt-0.5">{formatNextRun(nextRunAt)}</p>
        </div>
        <button
          onClick={handleViewPlan}
          className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white"
        >
          {t('dashboard:maintenance.viewPlan')}
        </button>
      </div>

      {showAllSchedulers && allSchedulers.length > 1 && (
        <div className="mt-3 pt-3 border-t border-slate-800/50">
          <p className="text-xs text-slate-500 mb-2">{t('dashboard:maintenance.schedulersTotal', { count: allSchedulers.length })}</p>
          <div className="flex flex-wrap gap-1.5">
            {allSchedulers.slice(0, 4).map((s) => (
              <span
                key={s.name}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                  s.is_enabled
                    ? 'bg-slate-800 text-slate-300'
                    : 'bg-slate-900 text-slate-500'
                }`}
              >
                <span>{getSchedulerIcon(s.name)}</span>
                {s.display_name.split(' ')[0]}
              </span>
            ))}
            {allSchedulers.length > 4 && (
              <span className="text-xs text-slate-500">
                +{allSchedulers.length - 4} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NextMaintenanceWidget;
