// client/src/components/dashboard/panels/GaugePanel.tsx

interface GaugePanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    submeta?: string;
    progress: number;
    delta?: string;
    delta_tone?: 'increase' | 'decrease' | 'steady' | 'live';
  };
  onClick?: () => void;
}

export const GaugePanel: React.FC<GaugePanelProps> = ({ title, icon, accent, data, onClick }) => {
  const deltaToneClass = data.delta_tone === 'decrease'
    ? 'text-emerald-400'
    : data.delta_tone === 'increase'
      ? 'text-rose-300'
      : data.delta_tone === 'steady'
        ? 'text-slate-400'
        : 'text-sky-400';

  const deltaLabel = data.delta ?? 'Live';

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
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
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">{data.meta}</span>
          <span className={`${deltaToneClass} shrink-0`}>{deltaLabel}</span>
        </div>
        {data.submeta && (
          <div className="text-xs text-slate-500 truncate">{data.submeta}</div>
        )}
      </div>
      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent} transition-all duration-500`}
          style={{ width: `${Math.min(Math.max(data.progress, 0), 100)}%` }}
        />
      </div>
    </div>
  );
};
