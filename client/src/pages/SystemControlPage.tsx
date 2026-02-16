/**
 * System Control Page (Admin Only)
 *
 * Consolidated admin system control view with two-level navigation:
 * - Categories: Hardware, Storage, Network, System
 * - Sub-tabs within each category
 */

import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Zap, Fan, HardDrive, Archive, Shield, Server, History, Plug, Gauge, FolderOpen, Share2, Cpu, Globe, Settings } from 'lucide-react';
import PowerManagement from './PowerManagement';
import FanControl from './FanControl';
import RaidManagement from './RaidManagement';
import BackupSettings from '../components/BackupSettings';
import VpnManagement from '../components/VpnManagement';
import { ServicesTab } from '../components/services';
import VCLSettings from '../components/vcl/VCLSettings';
import TapoDeviceSettings from '../components/TapoDeviceSettings';
import { RateLimitsTab } from '../components/rate-limits';
import WebdavConnectionCard from '../components/webdav/WebdavConnectionCard';
import SambaManagementCard from '../components/samba/SambaManagementCard';

type TabType = 'energy' | 'fan' | 'raid' | 'backup' | 'vpn' | 'services' | 'vcl' | 'smart' | 'ratelimits' | 'webdav' | 'samba';
type CategoryType = 'hardware' | 'storage' | 'network' | 'system';

interface TabConfig {
  id: TabType;
  labelKey: string;
  icon: React.ReactNode;
}

interface CategoryConfig {
  id: CategoryType;
  labelKey: string;
  icon: React.ReactNode;
  tabs: TabConfig[];
}

const CATEGORIES: CategoryConfig[] = [
  {
    id: 'hardware',
    labelKey: 'systemControl.categories.hardware',
    icon: <Cpu className="h-4 w-4 sm:h-5 sm:w-5" />,
    tabs: [
      { id: 'energy', labelKey: 'systemControl.tabs.energy', icon: <Zap className="h-5 w-5" /> },
      { id: 'fan', labelKey: 'systemControl.tabs.fan', icon: <Fan className="h-5 w-5" /> },
    ],
  },
  {
    id: 'storage',
    labelKey: 'systemControl.categories.storage',
    icon: <HardDrive className="h-4 w-4 sm:h-5 sm:w-5" />,
    tabs: [
      { id: 'raid', labelKey: 'systemControl.tabs.raid', icon: <HardDrive className="h-5 w-5" /> },
      { id: 'backup', labelKey: 'systemControl.tabs.backup', icon: <Archive className="h-5 w-5" /> },
    ],
  },
  {
    id: 'network',
    labelKey: 'systemControl.categories.network',
    icon: <Globe className="h-4 w-4 sm:h-5 sm:w-5" />,
    tabs: [
      { id: 'vpn', labelKey: 'systemControl.tabs.vpn', icon: <Shield className="h-5 w-5" /> },
      { id: 'webdav', labelKey: 'systemControl.tabs.webdav', icon: <FolderOpen className="h-5 w-5" /> },
      { id: 'samba', labelKey: 'systemControl.tabs.samba', icon: <Share2 className="h-5 w-5" /> },
    ],
  },
  {
    id: 'system',
    labelKey: 'systemControl.categories.system',
    icon: <Settings className="h-4 w-4 sm:h-5 sm:w-5" />,
    tabs: [
      { id: 'services', labelKey: 'systemControl.tabs.services', icon: <Server className="h-5 w-5" /> },
      { id: 'vcl', labelKey: 'systemControl.tabs.vcl', icon: <History className="h-5 w-5" /> },
      { id: 'smart', labelKey: 'systemControl.tabs.smart', icon: <Plug className="h-5 w-5" /> },
      { id: 'ratelimits', labelKey: 'systemControl.tabs.rateLimits', icon: <Gauge className="h-5 w-5" /> },
    ],
  },
];

// Auto-generated lookup: tab → category
const TAB_TO_CATEGORY: Record<TabType, CategoryType> = Object.fromEntries(
  CATEGORIES.flatMap((cat) => cat.tabs.map((tab) => [tab.id, cat.id]))
) as Record<TabType, CategoryType>;

// All valid tab IDs for validation
const VALID_TABS = new Set(CATEGORIES.flatMap((cat) => cat.tabs.map((tab) => tab.id)));

export default function SystemControlPage() {
  const { t } = useTranslation('common');
  const [searchParams, setSearchParams] = useSearchParams();

  // Get active tab from URL, default to 'energy'
  const rawTab = searchParams.get('tab') || 'energy';
  const activeTab = (VALID_TABS.has(rawTab as TabType) ? rawTab : 'energy') as TabType;

  // Derive active category from active tab
  const activeCategory = TAB_TO_CATEGORY[activeTab];
  const activeCategoryConfig = CATEGORIES.find((c) => c.id === activeCategory)!;

  // Tab change handler that updates URL
  const handleTabChange = (tab: TabType) => {
    setSearchParams({ tab });
  };

  // Category click → navigate to first tab of that category
  const handleCategoryChange = (category: CategoryType) => {
    const cat = CATEGORIES.find((c) => c.id === category)!;
    setSearchParams({ tab: cat.tabs[0].id });
  };

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            {t('navigation.systemControl')}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('navigation.systemControlDesc')}
          </p>
        </div>
      </div>

      {/* Two-Level Navigation */}
      <div className="space-y-3">
        {/* Category Pills */}
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
          <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => handleCategoryChange(cat.id)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                  activeCategory === cat.id
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                    : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                }`}
              >
                {cat.icon}
                <span>{t(cat.labelKey)}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Sub-Tabs (only for active category) */}
        <div className="relative">
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
            <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
              {activeCategoryConfig.tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    activeTab === tab.id
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  {tab.icon}
                  <span>{t(tab.labelKey)}</span>
                </button>
              ))}
            </div>
          </div>
          {/* Fade-Gradient rechts — nur mobile */}
          <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
        </div>
      </div>

      {/* Tab Content */}
      <div className="min-w-0">
        {activeTab === 'energy' && <PowerManagement isAdmin={true} />}
        {activeTab === 'fan' && <FanControl />}
        {activeTab === 'raid' && <RaidManagement />}
        {activeTab === 'backup' && <BackupSettings />}
        {activeTab === 'vpn' && <VpnManagement />}
        {activeTab === 'services' && <ServicesTab isAdmin={true} />}
        {activeTab === 'vcl' && <VCLSettings />}
        {activeTab === 'smart' && <TapoDeviceSettings />}
        {activeTab === 'ratelimits' && <RateLimitsTab />}
        {activeTab === 'webdav' && <WebdavConnectionCard />}
        {activeTab === 'samba' && <SambaManagementCard />}
      </div>
    </div>
  );
}
