import { useTranslation } from 'react-i18next';
import { Users, Share2, Cloud } from 'lucide-react';
import type { SharesTab } from './types';

interface SharesTabBarProps {
  activeTab: SharesTab;
  onChange: (tab: SharesTab) => void;
}

export function SharesTabBar({ activeTab, onChange }: SharesTabBarProps) {
  const { t } = useTranslation(['shares', 'common']);
  const tabs = [
    { key: 'shares' as const, label: t('tabs.userShares'), shortLabel: t('tabs.shares'), icon: Users },
    { key: 'shared-with-me' as const, label: t('tabs.sharedWithMe'), shortLabel: t('tabs.received'), icon: Share2 },
    { key: 'cloud-exports' as const, label: t('tabs.cloudExports', 'Cloud Shares'), shortLabel: t('tabs.cloudExportsShort', 'Cloud'), icon: Cloud },
  ];

  return (
    <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
      <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all touch-manipulation active:scale-95 ${
              activeTab === tab.key
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.label}</span>
            <span className="sm:hidden">{tab.shortLabel}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
