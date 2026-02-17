import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { FanScheduleEntry } from '../../api/fan-control';

interface ScheduleTimelineProps {
  entries: FanScheduleEntry[];
  activeEntryId?: number | null;
}

const COLORS = [
  'bg-sky-500/60',
  'bg-emerald-500/60',
  'bg-amber-500/60',
  'bg-purple-500/60',
  'bg-rose-500/60',
  'bg-teal-500/60',
  'bg-orange-500/60',
  'bg-indigo-500/60',
];

function timeToMinutes(time: string): number {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

function minutesToPercent(minutes: number): number {
  return (minutes / 1440) * 100;
}

export default function ScheduleTimeline({ entries, activeEntryId }: ScheduleTimelineProps) {
  const { t } = useTranslation(['system']);

  const enabledEntries = useMemo(
    () => entries.filter(e => e.is_enabled),
    [entries]
  );

  // Current time indicator position
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  const currentPercent = minutesToPercent(currentMinutes);

  const hourMarkers = [0, 3, 6, 9, 12, 15, 18, 21];

  return (
    <div className="mb-4">
      <h3 className="text-sm font-medium text-slate-400 mb-2">
        {t('system:fanControl.schedule.timeline')}
      </h3>

      {/* Timeline bar */}
      <div className="relative h-10 bg-slate-800 rounded-lg overflow-hidden border border-slate-700">
        {/* Schedule entry blocks */}
        {enabledEntries.map((entry, index) => {
          const start = timeToMinutes(entry.start_time);
          const end = timeToMinutes(entry.end_time);
          const color = COLORS[index % COLORS.length];
          const isActive = entry.id === activeEntryId;
          const borderClass = isActive ? 'ring-2 ring-emerald-400' : '';

          if (start <= end) {
            // Normal window
            const left = minutesToPercent(start);
            const width = minutesToPercent(end - start);
            return (
              <div
                key={entry.id}
                className={`absolute top-0 bottom-0 ${color} ${borderClass} flex items-center justify-center`}
                style={{ left: `${left}%`, width: `${width}%`, minWidth: '2px' }}
                title={`${entry.name}: ${entry.start_time}–${entry.end_time}`}
              >
                {width > 8 && (
                  <span className="text-[10px] text-white font-medium truncate px-1">
                    {entry.name}
                  </span>
                )}
              </div>
            );
          } else {
            // Overnight window — render as two blocks
            const leftWidth = minutesToPercent(1440 - start);
            const rightWidth = minutesToPercent(end);
            return (
              <div key={entry.id}>
                <div
                  className={`absolute top-0 bottom-0 ${color} ${borderClass} flex items-center justify-center`}
                  style={{ left: `${minutesToPercent(start)}%`, width: `${leftWidth}%`, minWidth: '2px' }}
                  title={`${entry.name}: ${entry.start_time}–${entry.end_time}`}
                >
                  {leftWidth > 8 && (
                    <span className="text-[10px] text-white font-medium truncate px-1">
                      {entry.name}
                    </span>
                  )}
                </div>
                <div
                  className={`absolute top-0 bottom-0 ${color} ${borderClass}`}
                  style={{ left: '0%', width: `${rightWidth}%`, minWidth: '2px' }}
                  title={`${entry.name}: ${entry.start_time}–${entry.end_time}`}
                />
              </div>
            );
          }
        })}

        {/* Current time indicator */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-rose-400 z-10"
          style={{ left: `${currentPercent}%` }}
        >
          <div className="absolute -top-1 -left-1 w-2.5 h-2.5 bg-rose-400 rounded-full" />
        </div>
      </div>

      {/* Hour labels */}
      <div className="relative h-4 mt-1">
        {hourMarkers.map(hour => (
          <span
            key={hour}
            className="absolute text-[10px] text-slate-500 -translate-x-1/2"
            style={{ left: `${minutesToPercent(hour * 60)}%` }}
          >
            {String(hour).padStart(2, '0')}
          </span>
        ))}
        <span
          className="absolute text-[10px] text-slate-500 -translate-x-full"
          style={{ left: '100%' }}
        >
          24
        </span>
      </div>
    </div>
  );
}
