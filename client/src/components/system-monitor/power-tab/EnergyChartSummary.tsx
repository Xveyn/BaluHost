import { useTranslation } from 'react-i18next';
import type { CumulativeEnergyResponse } from '../../../api/energy';
import { formatNumber } from '../../../lib/formatters';

interface EnergyChartSummaryProps {
  chartMode: 'cumulative' | 'instant';
  cumulativeData: CumulativeEnergyResponse;
}

export function EnergyChartSummary({ chartMode, cumulativeData }: EnergyChartSummaryProps) {
  const { t } = useTranslation(['system', 'common']);

  if (chartMode === 'instant') {
    const wattsValues = cumulativeData.data_points.map(dp => dp.instant_watts);
    const avgWatts = wattsValues.length > 0 ? wattsValues.reduce((a, b) => a + b, 0) / wattsValues.length : 0;
    const maxWatts = wattsValues.length > 0 ? Math.max(...wattsValues) : 0;
    const minWatts = wattsValues.length > 0 ? Math.min(...wattsValues) : 0;
    return (
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-400">{t('monitor.power.avgPower')}</p>
          <p className="text-lg font-semibold text-amber-400">
            {formatNumber(avgWatts, 1)} <span className="text-sm text-slate-400">W</span>
          </p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-400">{t('monitor.power.maxPower')}</p>
          <p className="text-lg font-semibold text-red-400">
            {formatNumber(maxWatts, 1)} <span className="text-sm text-slate-400">W</span>
          </p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-400">{t('monitor.power.minPower')}</p>
          <p className="text-lg font-semibold text-emerald-400">
            {formatNumber(minWatts, 1)} <span className="text-sm text-slate-400">W</span>
          </p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-400">{t('monitor.power.dataPoints')}</p>
          <p className="text-lg font-semibold text-slate-300">
            {cumulativeData.data_points.length}
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      <div className="bg-slate-800/50 rounded-lg p-3">
        <p className="text-xs text-slate-400">{t('monitor.power.totalConsumption')}</p>
        <p className="text-lg font-semibold text-emerald-400">
          {formatNumber(cumulativeData.total_kwh, 3)} <span className="text-sm text-slate-400">kWh</span>
        </p>
      </div>
      <div className="bg-slate-800/50 rounded-lg p-3">
        <p className="text-xs text-slate-400">{t('monitor.power.totalCosts')}</p>
        <p className="text-lg font-semibold text-orange-400">
          {formatNumber(cumulativeData.total_cost, 2)} <span className="text-sm text-slate-400">{cumulativeData.currency}</span>
        </p>
      </div>
      <div className="bg-slate-800/50 rounded-lg p-3">
        <p className="text-xs text-slate-400">{t('monitor.power.electricityPrice')}</p>
        <p className="text-lg font-semibold text-slate-300">
          {formatNumber(cumulativeData.cost_per_kwh, 2)} <span className="text-sm text-slate-400">{cumulativeData.currency}/kWh</span>
        </p>
      </div>
      <div className="bg-slate-800/50 rounded-lg p-3">
        <p className="text-xs text-slate-400">{t('monitor.power.dataPoints')}</p>
        <p className="text-lg font-semibold text-slate-300">
          {cumulativeData.data_points.length}
        </p>
      </div>
    </div>
  );
}
