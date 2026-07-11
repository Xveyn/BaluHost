import { useTranslation } from 'react-i18next';

type ChartMode = 'cumulative' | 'instant';
type CumulativePeriod = 'today' | 'week' | 'month' | 'custom';

interface ChartModePeriodControlsProps {
  chartMode: ChartMode;
  onModeChange: (m: ChartMode) => void;
  cumulativePeriod: CumulativePeriod;
  onPeriodChange: (p: CumulativePeriod) => void;
  customRange: React.ReactNode;
}

export function ChartModePeriodControls({
  chartMode,
  onModeChange,
  cumulativePeriod,
  onPeriodChange,
  customRange,
}: ChartModePeriodControlsProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="flex gap-1 sm:gap-2 flex-wrap">
      {/* Chart Mode Toggle */}
      {(['cumulative', 'instant'] as ChartMode[]).map((mode) => (
        <button
          key={mode}
          onClick={() => onModeChange(mode)}
          className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
            chartMode === mode
              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
          }`}
        >
          {mode === 'cumulative' ? t('monitor.power.modeCumulative') : t('monitor.power.modeInstant')}
        </button>
      ))}

      <div className="w-px bg-slate-700 mx-1 self-stretch" />

      {/* Period Selector */}
      {(['today', 'week', 'month'] as CumulativePeriod[]).map((period) => (
        <button
          key={period}
          onClick={() => onPeriodChange(period)}
          className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
            cumulativePeriod === period
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
          }`}
        >
          {period === 'today' ? t('monitor.power.periodToday') : period === 'week' ? t('monitor.power.periodWeek') : t('monitor.power.periodMonth')}
        </button>
      ))}
      {customRange}
    </div>
  );
}
