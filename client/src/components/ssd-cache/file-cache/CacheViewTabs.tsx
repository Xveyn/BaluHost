import { Zap, ArrowRightLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TabView } from '../../../hooks/useSsdFileCache';

export function CacheViewTabs({
  tabView,
  onSelect,
}: {
  tabView: TabView;
  onSelect: (v: TabView) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => onSelect('cache')}
        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${
          tabView === 'cache'
            ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
            : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
        }`}
      >
        <Zap className="w-4 h-4" />
        {t('ssdCache.migration.cacheTab', 'File Cache')}
      </button>
      <button
        onClick={() => onSelect('migration')}
        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${
          tabView === 'migration'
            ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
            : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
        }`}
      >
        <ArrowRightLeft className="w-4 h-4" />
        {t('ssdCache.migration.title', 'Data Migration')}
      </button>
    </div>
  );
}
