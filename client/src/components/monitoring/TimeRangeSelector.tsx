/**
 * Time range selector for monitoring charts
 */

import { useTranslation } from 'react-i18next';
import type { TimeRange } from '../../api/monitoring';

export interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
  className?: string;
}

const TIME_RANGE_KEYS: TimeRange[] = ['10m', '1h', '24h', '7d'];

export default function TimeRangeSelector({
  value,
  onChange,
  className = '',
}: TimeRangeSelectorProps) {
  const { t } = useTranslation(['system', 'admin']);

  const TIME_RANGES = TIME_RANGE_KEYS.map((r) => ({
    value: r,
    label: t(`admin:monitoring.timeRanges.${r}`),
  }));

  return (
    <div className={`flex gap-1 sm:gap-2 ${className}`}>
      {TIME_RANGES.map((range) => (
        <button
          key={range.value}
          onClick={() => onChange(range.value)}
          className={`rounded-lg px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium transition-all ${
            value === range.value
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
              : 'text-slate-400 hover:bg-slate-800 border border-slate-700/50 hover:border-slate-600'
          }`}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}
