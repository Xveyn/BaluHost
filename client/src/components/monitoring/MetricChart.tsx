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
}

const formatTime = (timestamp: string | number): string => {
  const date = new Date(timestamp);
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
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis
          dataKey="time"
          stroke="#94a3b8"
          tick={{ fill: '#94a3b8', fontSize: 12 }}
          tickLine={{ stroke: '#334155' }}
        />
        <YAxis
          stroke="#94a3b8"
          tick={{ fill: '#94a3b8', fontSize: 12 }}
          tickLine={{ stroke: '#334155' }}
          domain={yAxisDomain}
          label={
            yAxisLabel
              ? {
                  value: yAxisLabel,
                  angle: -90,
                  position: 'insideLeft',
                  style: { fill: '#94a3b8', fontSize: 12 },
                }
              : undefined
          }
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '8px',
            color: '#f1f5f9',
          }}
          labelStyle={{ color: '#94a3b8' }}
        />
        <Legend wrapperStyle={{ color: '#94a3b8' }} iconType="line" />
        {lines.map((line) =>
          showArea ? (
            <Area
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              stroke={line.color}
              fill={line.color}
              fillOpacity={0.1}
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
