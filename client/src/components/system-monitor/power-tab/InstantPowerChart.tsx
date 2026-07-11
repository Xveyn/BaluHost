import { useTranslation } from 'react-i18next';
import {
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { formatTimeForRange, parseUtcTimestamp } from '../../../lib/dateUtils';
import type { ChartTimeRange } from '../../../lib/dateUtils';
import type { CumulativeEnergyResponse } from '../../../api/energy';
import { formatNumber } from '../../../lib/formatters';

interface InstantPowerChartProps {
  cumulativeData: CumulativeEnergyResponse;
  cumulativePeriod: 'today' | 'week' | 'month' | 'custom';
  language: string;
}

export function InstantPowerChart({ cumulativeData, cumulativePeriod, language }: InstantPowerChartProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <ComposedChart
      data={cumulativeData.data_points.map((dp) => ({
        time: formatTimeForRange(dp.timestamp, cumulativePeriod as ChartTimeRange, language),
        fullTime: parseUtcTimestamp(dp.timestamp).toLocaleString(language),
        watts: dp.instant_watts,
      }))}
      margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
    >
      <defs>
        <linearGradient id="colorWatts" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
          <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
      <XAxis
        dataKey="time"
        stroke="#64748b"
        fontSize={11}
        tickLine={false}
        interval="preserveStartEnd"
        minTickGap={cumulativePeriod === 'week' ? 70 : 40}
      />
      <YAxis
        stroke="#f59e0b"
        fontSize={11}
        tickLine={false}
        axisLine={false}
        tickFormatter={(v) => formatNumber(v, 1)}
        label={{ value: 'W', angle: -90, position: 'insideLeft', fill: '#f59e0b', fontSize: 11 }}
      />
      <Tooltip
        contentStyle={{
          backgroundColor: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '8px',
          fontSize: '12px',
        }}
        labelStyle={{ color: '#94a3b8' }}
        formatter={(value: number) => [`${formatNumber(value, 1)} W`, t('monitor.power.powerLabel')]}
        labelFormatter={(label, payload) => {
          if (payload && payload[0]) {
            return payload[0].payload.fullTime;
          }
          return label;
        }}
      />
      <Legend
        wrapperStyle={{ fontSize: '12px' }}
        formatter={() => t('monitor.power.powerWatts')}
      />
      <Area
        type="monotone"
        dataKey="watts"
        stroke="#f59e0b"
        strokeWidth={2}
        fill="url(#colorWatts)"
        name="watts"
      />
    </ComposedChart>
  );
}
