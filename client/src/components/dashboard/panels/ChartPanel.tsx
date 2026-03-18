// client/src/components/dashboard/panels/ChartPanel.tsx
import { AreaChart, Area, ResponsiveContainer } from 'recharts';

interface ChartPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    points: number[];
  };
  onClick?: () => void;
}

export const ChartPanel: React.FC<ChartPanelProps> = ({ title, icon, accent, data, onClick }) => {
  const chartData = data.points.map((v, i) => ({ idx: i, value: v }));

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">{data.value}</p>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
          {icon}
        </div>
      </div>
      <div className="mt-2 text-xs text-slate-400 truncate">{data.meta}</div>
      <div className="mt-3 h-16 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="panelChartGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="value"
              stroke="#38bdf8"
              strokeWidth={1.5}
              fill="url(#panelChartGrad)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
