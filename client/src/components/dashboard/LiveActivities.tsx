import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Clock, Wind, HardDrive, Zap, ChevronRight, ChevronDown, Activity } from 'lucide-react';
import type { LiveActivityItem } from '../../hooks/useLiveActivities';

const ICONS = {
  clock: Clock,
  wind: Wind,
  'hard-drive': HardDrive,
  zap: Zap,
} as const;

interface LiveActivitiesProps {
  activities: LiveActivityItem[];
}

export function LiveActivities({ activities }: LiveActivitiesProps) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');

  if (activities.length === 0) return null;

  const hasWarning = activities.some((a) => a.level === 'warning');
  const dotColor = hasWarning ? 'bg-amber-400' : 'bg-sky-400';

  return (
    <div className="rounded-2xl border border-slate-800/50 bg-slate-900/55 overflow-hidden">
      {/* Collapsible header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-800/40"
      >
        <span className={`inline-flex h-2 w-2 shrink-0 rounded-full animate-pulse ${dotColor}`} />
        <Activity className="h-4 w-4 shrink-0 text-slate-400" />
        <span className="text-sm font-medium text-slate-200">
          {t('liveActivities.title')}
        </span>
        <span className="rounded-full border border-slate-700/60 bg-slate-800/60 px-2 py-0.5 text-xs tabular-nums text-slate-400">
          {t('liveActivities.count', { count: activities.length })}
        </span>
        <span className="flex-1" />
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Expandable list */}
      <div
        className={`grid transition-[grid-template-rows] duration-200 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <div className="divide-y divide-slate-800/40 border-t border-slate-800/40">
            {activities.map((activity) => {
              const Icon = ICONS[activity.icon];
              const isWarning = activity.level === 'warning';

              const rowDotColor = isWarning ? 'bg-amber-400' : 'bg-sky-400';
              const iconColor = isWarning ? 'text-amber-400' : 'text-sky-400';
              const progressBg = isWarning
                ? 'bg-gradient-to-r from-amber-500 to-orange-500'
                : 'bg-gradient-to-r from-sky-500 to-indigo-500';

              return (
                <button
                  key={activity.id}
                  onClick={() => activity.link && navigate(activity.link)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-800/40"
                >
                  <span className={`inline-flex h-2 w-2 shrink-0 rounded-full animate-pulse ${rowDotColor}`} />
                  <Icon className={`h-4 w-4 shrink-0 ${iconColor}`} />
                  <span className="min-w-0 flex-1 text-sm text-slate-200 truncate">
                    {t(activity.label, activity.labelParams)}
                  </span>
                  {activity.progress != null && (
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className={`h-full rounded-full ${progressBg} transition-all duration-500`}
                          style={{ width: `${Math.min(Math.max(activity.progress, 0), 100)}%` }}
                        />
                      </div>
                      <span className="text-xs tabular-nums text-slate-400 w-8 text-right">
                        {Math.round(activity.progress)}%
                      </span>
                    </div>
                  )}
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" />
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
