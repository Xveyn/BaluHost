// client/src/components/dashboard/panels/StatPanel.tsx

interface StatPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    submeta?: string;
  };
  onClick?: () => void;
}

export const StatPanel: React.FC<StatPanelProps> = ({ title, icon, accent, data, onClick }) => {
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
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="text-xs text-slate-400 truncate">{data.meta}</div>
        {data.submeta && (
          <div className="text-xs text-slate-500 truncate">{data.submeta}</div>
        )}
      </div>
    </div>
  );
};
