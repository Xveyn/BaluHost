/**
 * Time range selector for monitoring charts
 */

import type { TimeRange } from '../../api/monitoring';

export interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
  className?: string;
}

const TIME_RANGES: { value: TimeRange; label: string }[] = [
  { value: '10m', label: '10 Min' },
  { value: '1h', label: '1 Std' },
  { value: '24h', label: '24 Std' },
  { value: '7d', label: '7 Tage' },
];

export default function TimeRangeSelector({
  value,
  onChange,
  className = '',
}: TimeRangeSelectorProps) {
  return (
    <div className={`flex gap-2 ${className}`}>
      {TIME_RANGES.map((range) => (
        <button
          key={range.value}
          onClick={() => onChange(range.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
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
