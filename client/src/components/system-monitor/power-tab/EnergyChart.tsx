import { useTranslation } from 'react-i18next';
import { ResponsiveContainer } from 'recharts';
import type { CumulativeEnergyResponse } from '../../../api/energy';
import { CumulativeEnergyChart } from './CumulativeEnergyChart';
import { InstantPowerChart } from './InstantPowerChart';

interface EnergyChartProps {
  chartMode: 'cumulative' | 'instant';
  cumulativeData: CumulativeEnergyResponse | null;
  cumulativeLoading: boolean;
  cumulativePeriod: 'today' | 'week' | 'month' | 'custom';
  language: string;
}

export function EnergyChart({ chartMode, cumulativeData, cumulativeLoading, cumulativePeriod, language }: EnergyChartProps) {
  const { t } = useTranslation(['system', 'common']);

  return cumulativeLoading ? (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
    </div>
  ) : cumulativeData && cumulativeData.data_points.length > 0 ? (
    <div className="h-[300px] sm:h-[350px]">
      <ResponsiveContainer width="100%" height="100%">
        {chartMode === 'cumulative' ? (
          <CumulativeEnergyChart
            cumulativeData={cumulativeData}
            cumulativePeriod={cumulativePeriod}
            language={language}
          />
        ) : (
          <InstantPowerChart
            cumulativeData={cumulativeData}
            cumulativePeriod={cumulativePeriod}
            language={language}
          />
        )}
      </ResponsiveContainer>
    </div>
  ) : (
    <div className="text-center py-8 text-slate-400">
      {t('monitor.noDataForPeriod')}
    </div>
  );
}
