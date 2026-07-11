import { useTranslation } from 'react-i18next';
import {
  ComposedChart,
  Area,
  Line,
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

interface CumulativeEnergyChartProps {
  cumulativeData: CumulativeEnergyResponse;
  cumulativePeriod: 'today' | 'week' | 'month' | 'custom';
  language: string;
}

export function CumulativeEnergyChart({ cumulativeData, cumulativePeriod, language }: CumulativeEnergyChartProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <ComposedChart
      data={cumulativeData.data_points.map((dp) => ({
        time: formatTimeForRange(dp.timestamp, cumulativePeriod as ChartTimeRange, language),
        fullTime: parseUtcTimestamp(dp.timestamp).toLocaleString(language),
        kwh: dp.cumulative_kwh,
        cost: dp.cumulative_cost,
        watts: dp.instant_watts,
      }))}
      margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
    >
      <defs>
        <linearGradient id="colorKwh" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
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
        yAxisId="left"
        stroke="#10b981"
        fontSize={11}
        tickLine={false}
        axisLine={false}
        tickFormatter={(v) => formatNumber(v, 2)}
        label={{ value: 'kWh', angle: -90, position: 'insideLeft', fill: '#10b981', fontSize: 11 }}
      />
      <YAxis
        yAxisId="right"
        orientation="right"
        stroke="#f97316"
        fontSize={11}
        tickLine={false}
        axisLine={false}
        tickFormatter={(v) => formatNumber(v, 2)}
        label={{ value: cumulativeData.currency, angle: 90, position: 'insideRight', fill: '#f97316', fontSize: 11 }}
      />
      <Tooltip
        contentStyle={{
          backgroundColor: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '8px',
          fontSize: '12px',
        }}
        labelStyle={{ color: '#94a3b8' }}
        formatter={(value: number, name: string) => {
          if (name === 'kwh') return [`${formatNumber(value, 4)} kWh`, t('monitor.power.consumption')];
          if (name === 'cost') return [`${formatNumber(value, 4)} ${cumulativeData.currency}`, t('monitor.power.costsLabel')];
          if (name === 'watts') return [`${formatNumber(value, 1)} W`, t('monitor.power.powerLabel')];
          return [value, name];
        }}
        labelFormatter={(label, payload) => {
          if (payload && payload[0]) {
            return payload[0].payload.fullTime;
          }
          return label;
        }}
      />
      <Legend
        wrapperStyle={{ fontSize: '12px' }}
        formatter={(value) => {
          if (value === 'kwh') return t('monitor.power.consumptionKwh');
          if (value === 'cost') return `${t('monitor.power.costsLabel')} (${cumulativeData.currency})`;
          return value;
        }}
      />
      <Area
        yAxisId="left"
        type="monotone"
        dataKey="kwh"
        stroke="#10b981"
        strokeWidth={2}
        fill="url(#colorKwh)"
        name="kwh"
      />
      <Line
        yAxisId="right"
        type="monotone"
        dataKey="cost"
        stroke="#f97316"
        strokeWidth={2}
        dot={false}
        name="cost"
      />
    </ComposedChart>
  );
}
