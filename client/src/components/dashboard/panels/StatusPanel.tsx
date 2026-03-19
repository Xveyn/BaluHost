// client/src/components/dashboard/panels/StatusPanel.tsx

interface StatusItem {
  label: string;
  value: string;
  tone: 'ok' | 'warning' | 'error' | 'neutral';
}

interface StatusPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    items: StatusItem[];
  };
  onClick?: () => void;
}

const toneColors: Record<string, string> = {
  ok: 'bg-emerald-400',
  warning: 'bg-amber-400',
  error: 'bg-rose-400',
  neutral: 'bg-slate-400',
};

export const StatusPanel: React.FC<StatusPanelProps> = ({ title, icon, accent, data, onClick }) => {
  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3 mb-4">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${accent} text-white`}>
          {icon}
        </div>
      </div>
      <ul className="space-y-2">
        {data.items.map((item, i) => (
          <li key={i} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${toneColors[item.tone] || toneColors.neutral}`} />
              <span className="text-slate-400">{item.label}</span>
            </div>
            <span className="text-slate-200">{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};
