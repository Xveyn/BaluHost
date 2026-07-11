import type React from 'react';
import type { Delta } from '../../hooks/useDashboardStats';

export interface QuickStat {
  id: string;
  title: string;
  value: string;
  meta: string;
  submeta?: string;
  delta: Delta;
  accent: string;
  progress: number;
  icon: React.ReactNode;
}

interface QuickStatCardProps {
  stat: QuickStat;
  onClick?: () => void;
}

export function QuickStatCard({ stat, onClick }: QuickStatCardProps): JSX.Element {
  const deltaToneClass = stat.delta.tone === 'decrease'
    ? 'text-emerald-400'
    : stat.delta.tone === 'increase'
      ? 'text-rose-300'
      : stat.delta.tone === 'steady'
        ? 'text-slate-400'
        : 'text-sky-400';

  const isClickable = !!onClick;

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] active:scale-[0.98] touch-manipulation ${isClickable ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{stat.title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">{stat.value}</p>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${stat.accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
          {stat.icon}
        </div>
      </div>
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">{stat.meta}</span>
          <span className={`${deltaToneClass} shrink-0`}>{stat.delta.label}</span>
        </div>
        {stat.submeta && (
          <div className="text-xs text-slate-500 truncate">
            {stat.submeta}
          </div>
        )}
      </div>
      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${stat.accent} transition-all duration-500`}
          style={{ width: `${Math.min(Math.max(stat.progress, 0), 100)}%` }}
        />
      </div>
    </div>
  );
}
