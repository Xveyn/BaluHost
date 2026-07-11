import { useTranslation } from 'react-i18next';
import type { LucideIcon } from 'lucide-react';
import { Plug, Store, BookOpen } from 'lucide-react';

export type TabType = 'plugins' | 'marketplace' | 'documentation';

export interface PluginTab {
  id: TabType;
  labelKey: string;
  icon: LucideIcon;
}

export const TABS: PluginTab[] = [
  { id: 'plugins' as TabType, labelKey: 'tabs.installed', icon: Plug },
  { id: 'marketplace' as TabType, labelKey: 'tabs.marketplace', icon: Store },
  { id: 'documentation' as TabType, labelKey: 'tabs.documentation', icon: BookOpen },
];

export function PluginTabNav({
  activeTab,
  onSelect,
}: {
  activeTab: TabType;
  onSelect: (id: TabType) => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="flex gap-2 border-b border-slate-800 pb-3 overflow-x-auto scrollbar-none">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelect(tab.id)}
          className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
            activeTab === tab.id
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
              : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
          }`}
        >
          <tab.icon className="w-4 h-4" />
          {t(tab.labelKey)}
        </button>
      ))}
    </div>
  );
}
