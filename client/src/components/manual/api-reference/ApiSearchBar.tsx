import { Search } from 'lucide-react';
import type { TFunction } from 'i18next';

export interface ApiSearchBarProps {
  value: string;
  onChange: (q: string) => void;
  t: TFunction;
}

export function ApiSearchBar({ value, onChange, t }: ApiSearchBarProps) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('system:apiCenter.searchPlaceholder', 'Search endpoints...')}
        className="w-full pl-10 pr-4 py-2.5 bg-slate-800/40 border border-slate-700/50 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors text-xs"
        >
          ✕
        </button>
      )}
    </div>
  );
}
