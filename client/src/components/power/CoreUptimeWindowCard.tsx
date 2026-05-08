/**
 * Per-window editable card for Core Operating Hours.
 *
 * Auto-saves on change. Optimistic update; on API error, parent reverts.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';
import type { CoreUptimeWindow, CoreUptimeWindowUpdate } from '../../api/coreUptime';

const WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

interface Props {
  window: CoreUptimeWindow;
  onChange: (id: number, patch: CoreUptimeWindowUpdate) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

export function CoreUptimeWindowCard({ window: w, onChange, onDelete }: Props) {
  const { t } = useTranslation('system');
  const [label, setLabel] = useState(w.label ?? '');

  const crossesMidnight =
    w.end_time < w.start_time && w.end_time !== w.start_time;

  const toggleWeekday = (day: number) => {
    const next = w.weekdays.includes(day)
      ? w.weekdays.filter((d) => d !== day)
      : [...w.weekdays, day].sort();
    if (next.length === 0) return; // require at least one
    onChange(w.id, { weekdays: next });
  };

  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 sm:p-4 space-y-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange(w.id, { enabled: !w.enabled })}
          className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors ${
            w.enabled ? 'bg-teal-500' : 'bg-slate-600'
          }`}
          aria-label={t('sleep.coreUptime.enableWindow')}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${
              w.enabled ? 'translate-x-4 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => {
            if (label !== (w.label ?? '')) {
              onChange(w.id, { label: label || null });
            }
          }}
          placeholder={t('sleep.coreUptime.labelPlaceholder')}
          className="flex-1 rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => onDelete(w.id)}
          className="rounded p-1.5 text-slate-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
          title={t('sleep.coreUptime.deleteTitle')}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-wrap gap-1">
        {WEEKDAY_KEYS.map((key, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => toggleWeekday(idx)}
            className={`min-w-[2rem] rounded px-2 py-1 text-xs font-medium transition-colors ${
              w.weekdays.includes(idx)
                ? 'bg-teal-500/20 text-teal-300 border border-teal-500/40'
                : 'bg-slate-800/40 text-slate-500 border border-slate-700/40 hover:text-slate-300'
            }`}
          >
            {t(`sleep.coreUptime.weekdays.${key}`)}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="time"
          value={w.start_time}
          onChange={(e) => onChange(w.id, { start_time: e.target.value })}
          className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white focus:border-teal-400 focus:outline-none"
        />
        <span className="text-slate-500">→</span>
        <input
          type="time"
          value={w.end_time}
          onChange={(e) => onChange(w.id, { end_time: e.target.value })}
          className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white focus:border-teal-400 focus:outline-none"
        />
        {crossesMidnight && (
          <span className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-0.5">
            {t('sleep.coreUptime.crossesMidnight')}
          </span>
        )}
      </div>
    </div>
  );
}
