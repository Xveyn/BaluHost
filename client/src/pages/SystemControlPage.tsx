/**
 * System Control Page (Admin Only)
 *
 * Consolidated admin system control view with tabs for:
 * - Energy (Power Management)
 * - Fan Control
 * - RAID Management
 * - Backup
 * - VPN
 * - Services (full control)
 * - VCL (Version Control)
 * - Smart Devices (Tapo)
 */

import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Zap, Fan, HardDrive, Archive, Shield, Server, History, Plug, Gauge, FolderOpen, Share2 } from 'lucide-react';
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

interface TabConfig {
  id: TabType;
  labelKey: string;
  icon: React.ReactNode;
}

const TABS: TabConfig[] = [
  {
    id: 'energy',
    labelKey: 'systemControl.tabs.energy',
    icon: <Zap className="h-5 w-5" />,
  },
  {
    id: 'fan',
    labelKey: 'systemControl.tabs.fan',
    icon: <Fan className="h-5 w-5" />,
  },
  {
    id: 'raid',
    labelKey: 'systemControl.tabs.raid',
    icon: <HardDrive className="h-5 w-5" />,
  },
  {
    id: 'backup',
    labelKey: 'systemControl.tabs.backup',
    icon: <Archive className="h-5 w-5" />,
  },
  {
    id: 'vpn',
    labelKey: 'systemControl.tabs.vpn',
    icon: <Shield className="h-5 w-5" />,
  },
  {
    id: 'services',
    labelKey: 'systemControl.tabs.services',
    icon: <Server className="h-5 w-5" />,
  },
  {
    id: 'vcl',
    labelKey: 'systemControl.tabs.vcl',
    icon: <History className="h-5 w-5" />,
  },
  {
    id: 'smart',
    labelKey: 'systemControl.tabs.smart',
    icon: <Plug className="h-5 w-5" />,
  },
  {
    id: 'ratelimits',
    labelKey: 'systemControl.tabs.rateLimits',
    icon: <Gauge className="h-5 w-5" />,
  },
  {
    id: 'webdav',
    labelKey: 'systemControl.tabs.webdav',
    icon: <FolderOpen className="h-5 w-5" />,
  },
  {
    id: 'samba',
    labelKey: 'systemControl.tabs.samba',
    icon: <Share2 className="h-5 w-5" />,
  },
];

export default function SystemControlPage() {
  const { t } = useTranslation('common');
  const [searchParams, setSearchParams] = useSearchParams();

  // Get active tab from URL, default to 'energy'
  const activeTab = (searchParams.get('tab') || 'energy') as TabType;

  // Tab change handler that updates URL
  const handleTabChange = (tab: TabType) => {
    setSearchParams({ tab });
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

      {/* Tab Navigation */}
      <div className="relative">
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
          <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
            {TABS.map((tab) => (
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
                <span className="hidden sm:inline">{t(tab.labelKey)}</span>
              </button>
            ))}
          </div>
        </div>
        {/* Fade-Gradient rechts — nur mobile */}
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
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
