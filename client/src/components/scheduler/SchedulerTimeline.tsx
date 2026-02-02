import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, CheckCircle, XCircle, Loader2, ChevronUp } from 'lucide-react';
import type { SchedulerExecution, TimelineEntry } from '../../api/schedulers';
import { groupExecutionsByHour, getSchedulerIcon, getStatusBadgeClasses } from '../../api/schedulers';

interface SchedulerTimelineProps {
  executions: SchedulerExecution[];
  loading: boolean;
}

function TimelineBar({ entry, maxCount }: { entry: TimelineEntry; maxCount: number }) {
  const { t } = useTranslation(['scheduler']);
  const [isExpanded, setIsExpanded] = useState(false);
  const total = entry.completedCount + entry.failedCount + entry.runningCount;
  const barHeight = maxCount > 0 ? Math.max(4, (total / maxCount) * 48) : 0;

  return (
    <div className="flex flex-col items-center group relative">
      {/* Bar */}
      <div
        className="w-6 rounded-t cursor-pointer transition-all hover:opacity-80"
        style={{ height: `${barHeight}px` }}
        onClick={() => total > 0 && setIsExpanded(!isExpanded)}
      >
        {entry.failedCount > 0 && (
          <div
            className="w-full bg-red-500 rounded-t"
            style={{
              height: `${(entry.failedCount / total) * 100}%`,
            }}
          />
        )}
        {entry.runningCount > 0 && (
          <div
            className="w-full bg-blue-500"
            style={{
              height: `${(entry.runningCount / total) * 100}%`,
            }}
          />
        )}
        {entry.completedCount > 0 && (
          <div
            className="w-full bg-green-500 rounded-b"
            style={{
              height: `${(entry.completedCount / total) * 100}%`,
            }}
          />
        )}
      </div>

      {/* Hour label */}
      <div className="text-[10px] text-slate-500 mt-1 -rotate-45 origin-top-left w-8">
        {entry.hour}
      </div>

      {/* Tooltip on hover */}
      {total > 0 && (
        <div className="absolute bottom-full mb-2 hidden group-hover:block z-10">
          <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-lg whitespace-nowrap">
            <div className="font-medium text-white mb-1">{entry.hour}</div>
            <div className="flex flex-col gap-0.5">
              {entry.completedCount > 0 && (
                <span className="text-green-400">{entry.completedCount} {t('scheduler:timeline.completed')}</span>
              )}
              {entry.failedCount > 0 && (
                <span className="text-red-400">{entry.failedCount} {t('scheduler:timeline.failed')}</span>
              )}
              {entry.runningCount > 0 && (
                <span className="text-blue-400">{entry.runningCount} {t('scheduler:timeline.running')}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Expanded details */}
      {isExpanded && entry.executions.length > 0 && (
        <div className="absolute top-full mt-8 left-1/2 -translate-x-1/2 z-20 w-64">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-lg overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
              <span className="text-xs font-medium text-white">{entry.hour}</span>
              <button
                onClick={() => setIsExpanded(false)}
                className="text-slate-400 hover:text-white"
              >
                <ChevronUp className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-48 overflow-y-auto">
              {entry.executions.map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center gap-2 px-3 py-2 border-b border-slate-700/50 last:border-0"
                >
                  <span>{getSchedulerIcon(exec.scheduler_name)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-slate-200 truncate">
                      {exec.scheduler_name.replace(/_/g, ' ')}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {new Date(exec.started_at).toLocaleTimeString()}
                    </div>
                  </div>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${getStatusBadgeClasses(exec.status)}`}
                  >
                    {exec.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function SchedulerTimeline({ executions, loading }: SchedulerTimelineProps) {
  const { t } = useTranslation(['scheduler']);
  const timelineData = useMemo(() => groupExecutionsByHour(executions), [executions]);
  const maxCount = useMemo(
    () => Math.max(...timelineData.map((e) => e.completedCount + e.failedCount + e.runningCount), 1),
    [timelineData]
  );

  // Summary stats
  const totalCompleted = executions.filter((e) => e.status === 'completed').length;
  const totalFailed = executions.filter((e) => e.status === 'failed').length;
  const totalRunning = executions.filter((e) => e.status === 'running').length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Clock className="h-5 w-5 text-sky-400" />
          <h3 className="font-medium text-white">{t('scheduler:timeline.title')}</h3>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-slate-300">{totalCompleted}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <XCircle className="h-4 w-4 text-red-500" />
            <span className="text-slate-300">{totalFailed}</span>
          </div>
          {totalRunning > 0 && (
            <div className="flex items-center gap-1.5">
              <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
              <span className="text-slate-300">{totalRunning}</span>
            </div>
          )}
        </div>
      </div>

      {/* Timeline chart */}
      <div className="relative">
        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 bottom-8 w-8 flex flex-col justify-between text-[10px] text-slate-500">
          <span>{maxCount}</span>
          <span>{Math.floor(maxCount / 2)}</span>
          <span>0</span>
        </div>

        {/* Chart area */}
        <div className="ml-10">
          {/* Grid lines */}
          <div className="absolute left-10 right-0 top-0 h-12 border-b border-slate-800/50" />
          <div className="absolute left-10 right-0 top-6 border-b border-slate-800/30 border-dashed" />

          {/* Bars */}
          <div className="flex items-end justify-between h-12 gap-1 pb-0">
            {timelineData.map((entry, idx) => (
              <TimelineBar key={idx} entry={entry} maxCount={maxCount} />
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 mt-8 pt-4 border-t border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-green-500" />
          <span className="text-xs text-slate-400">{t('scheduler:status.completed')}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-red-500" />
          <span className="text-xs text-slate-400">{t('scheduler:status.failed')}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-blue-500" />
          <span className="text-xs text-slate-400">{t('scheduler:status.running')}</span>
        </div>
      </div>

      {/* Recent failed executions */}
      {totalFailed > 0 && (
        <div className="mt-6 pt-4 border-t border-slate-800">
          <h4 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
            <XCircle className="h-4 w-4 text-red-500" />
            {t('scheduler:timeline.recentFailures')}
          </h4>
          <div className="space-y-2">
            {executions
              .filter((e) => e.status === 'failed')
              .slice(0, 3)
              .map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center gap-3 p-3 bg-red-900/10 border border-red-900/30 rounded-lg"
                >
                  <span className="text-lg">{getSchedulerIcon(exec.scheduler_name)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-slate-200">
                      {exec.scheduler_name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                    </div>
                    <div className="text-xs text-slate-500">
                      {new Date(exec.started_at).toLocaleString()}
                    </div>
                  </div>
                  {exec.error_message && (
                    <div className="text-xs text-red-400 max-w-xs truncate" title={exec.error_message}>
                      {exec.error_message}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
