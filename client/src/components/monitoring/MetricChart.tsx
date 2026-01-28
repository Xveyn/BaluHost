/**
 * Shared metric chart component using Recharts
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import { parseUtcTimestamp } from '../../lib/dateUtils';

export interface ChartDataPoint {
  time: string;
  timestamp?: string | number;
  [key: string]: any;
}

export interface MetricLine {
  dataKey: string;
  name: string;
  color: string;
  strokeWidth?: number;
}

export interface MetricChartProps {
  data: ChartDataPoint[];
  lines: MetricLine[];
  yAxisLabel?: string;
  yAxisDomain?: [number | 'auto', number | 'auto'];
  height?: number;
  showArea?: boolean;
  loading?: boolean;
  emptyMessage?: string;
  compact?: boolean; // Compact mode for mini-charts (no axes, no legend)
}

const formatTime = (timestamp: string | number): string => {
  // Handle both string timestamps (from backend) and numeric (epoch ms)
  const date = typeof timestamp === 'string'
    ? parseUtcTimestamp(timestamp)
    : new Date(timestamp);
  return date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

export default function MetricChart({
  data,
  lines,
  yAxisLabel,
  yAxisDomain = ['auto', 'auto'],
  height = 300,
  showArea = false,
  loading = false,
  emptyMessage = 'Keine Daten verfügbar',
  compact = false,
}: MetricChartProps) {
  // Format data with time labels
  const chartData = data.map((point) => ({
    ...point,
    time: point.time || (point.timestamp ? formatTime(point.timestamp) : ''),
  }));

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
          <p className="mt-2 text-sm text-slate-400">Lade Daten...</p>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-center">
          <svg
            className="mx-auto h-12 w-12 text-slate-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
          <p className="mt-2 text-sm text-slate-400">{emptyMessage}</p>
        </div>
      </div>
    );
  }

  const ChartComponent = showArea ? AreaChart : LineChart;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ChartComponent data={chartData}>
        {!compact && <CartesianGrid strokeDasharray="3 3" stroke="#334155" />}
        <XAxis
          dataKey="time"
          stroke={compact ? 'transparent' : '#94a3b8'}
          tick={compact ? false : { fill: '#94a3b8', fontSize: 12 }}
          tickLine={compact ? false : { stroke: '#334155' }}
          axisLine={!compact}
          hide={compact}
        />
        <YAxis
          stroke={compact ? 'transparent' : '#94a3b8'}
          tick={compact ? false : { fill: '#94a3b8', fontSize: 12 }}
          tickLine={compact ? false : { stroke: '#334155' }}
          axisLine={!compact}
          domain={yAxisDomain}
          hide={compact}
          label={
            !compact && yAxisLabel
              ? {
                  value: yAxisLabel,
                  angle: -90,
                  position: 'insideLeft',
                  style: { fill: '#94a3b8', fontSize: 12 },
                }
              : undefined
          }
        />
        {!compact && (
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f1f5f9',
            }}
            labelStyle={{ color: '#94a3b8' }}
          />
        )}
        {!compact && <Legend wrapperStyle={{ color: '#94a3b8' }} iconType="line" />}
        {lines.map((line) =>
          showArea ? (
            <Area
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              stroke={line.color}
              fill={line.color}
              fillOpacity={compact ? 0.2 : 0.1}
              strokeWidth={line.strokeWidth || 2}
              name={line.name}
              dot={false}
              animationDuration={300}
            />
          ) : (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              stroke={line.color}
              strokeWidth={line.strokeWidth || 2}
              name={line.name}
              dot={false}
              animationDuration={300}
            />
          )
        )}
      </ChartComponent>
    </ResponsiveContainer>
  );
}
