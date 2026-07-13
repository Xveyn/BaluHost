import { Code, Gauge } from 'lucide-react';

export interface ApiViewToggleProps {
  activeView: 'docs' | 'limits';
  onChange: (v: 'docs' | 'limits') => void;
  t: (key: string) => string;
}

export function ApiViewToggle({ activeView, onChange, t }: ApiViewToggleProps) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onChange('docs')}
        className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
          activeView === 'docs'
            ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-lg shadow-cyan-500/10'
            : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
        }`}
      >
        <Code className="w-4 h-4" />
        <span>{t('system:apiCenter.tabs.apiDocs')}</span>
      </button>
      <button
        onClick={() => onChange('limits')}
        className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
          activeView === 'limits'
            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40 shadow-lg shadow-amber-500/10'
            : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
        }`}
      >
        <Gauge className="w-4 h-4" />
        <span>{t('system:apiCenter.tabs.rateLimits')}</span>
      </button>
    </div>
  );
}
