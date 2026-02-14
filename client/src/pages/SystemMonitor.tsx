/**
 * System Monitor Page
 *
 * Consolidated monitoring view with tabs for:
 * - CPU (usage, frequency, temperature)
 * - RAM (usage, percent)
 * - Network (download/upload speeds)
 * - Disk I/O (per-disk throughput, IOPS)
 * - Power (from Tapo devices if available)
 * - Services (backend service status)
 * - Health (system health overview)
 * - Logs (audit and file access logs)
 */

import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { TimeRangeSelector } from '../components/monitoring';
import type { TimeRange } from '../api/monitoring';
import { ServicesStatusTab } from '../components/services';
import { AdminBadge } from '../components/ui/AdminBadge';
import { HealthTab } from '../components/monitoring/HealthTab';
import { LogsTab } from '../components/monitoring/LogsTab';
import { ActivityTab } from '../components/monitoring/ActivityTab';
import { CpuTab } from '../components/system-monitor/CpuTab';
import { MemoryTab } from '../components/system-monitor/MemoryTab';
import { NetworkTab } from '../components/system-monitor/NetworkTab';
import { DiskIoTab } from '../components/system-monitor/DiskIoTab';
import { PowerTab } from '../components/system-monitor/PowerTab';

import type { User } from '../types/auth';

interface SystemMonitorProps {
  user: User;
}

type TabType = 'cpu' | 'memory' | 'network' | 'disk-io' | 'power' | 'services' | 'health' | 'logs' | 'activity';

interface TabConfig {
  id: TabType;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const TABS: TabConfig[] = [
  {
    id: 'cpu',
    label: 'CPU',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M9 9h6v6H9z" />
        <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'memory',
    label: 'RAM',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <path d="M6 10v4M10 10v4M14 10v4M18 10v4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'network',
    label: 'Netzwerk',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M5 12.55a11 11 0 0114.08 0M8.53 16.11a6 6 0 016.95 0M12 20h.01" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'disk-io',
    label: 'Disk I/O',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      </svg>
    ),
  },
  {
    id: 'power',
    label: 'Strom',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'services',
    label: 'Services',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'health',
    label: 'Gesundheit',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'logs',
    label: 'Protokolle',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M7 9h10" strokeLinecap="round" />
        <path d="M7 13h10" strokeLinecap="round" />
        <path d="M7 17h6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'activity',
    label: 'Aktivität',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

// Main Component
export default function SystemMonitor({ user }: SystemMonitorProps) {
  const { t } = useTranslation(['system', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');

  const isAdmin = user?.role === 'admin';

  // Get active tab from URL, default to 'cpu'
  const activeTab = (searchParams.get('tab') || 'cpu') as TabType;

  // Tab change handler that updates URL
  const handleTabChange = (tab: TabType) => {
    setSearchParams({ tab });
  };

  // Filter tabs based on admin status
  const visibleTabs = useMemo(() => {
    return TABS.filter(tab => !tab.adminOnly || isAdmin);
  }, [isAdmin]);

  // Translate tab labels
  const getTabLabel = (tabId: TabType): string => {
    const tabKeyMap: Record<TabType, string> = {
      'cpu': 'monitor.tabs.cpu',
      'memory': 'monitor.tabs.memory',
      'network': 'monitor.tabs.network',
      'disk-io': 'monitor.tabs.diskIo',
      'power': 'monitor.tabs.power',
      'services': 'monitor.tabs.services',
      'health': 'monitor.tabs.health',
      'logs': 'monitor.tabs.logs',
      'activity': 'monitor.tabs.activity',
    };
    return t(tabKeyMap[tabId]);
  };

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('monitor.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('monitor.subtitleLong')}
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          {['cpu', 'memory', 'network', 'disk-io'].includes(activeTab) && (
            <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          )}
          <div className="rounded-full border border-slate-800 bg-slate-900/70 px-3 sm:px-4 py-1.5 sm:py-2 text-xs text-slate-400 shadow-inner">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400 inline-block mr-2" />
            {t('monitor.live')}
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="relative">
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
          <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
            {visibleTabs.map((tab) => (
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
                <span className="hidden sm:inline">{getTabLabel(tab.id)}</span>
                <span className="sm:hidden">{getTabLabel(tab.id).slice(0, 3)}</span>
                {tab.adminOnly && <AdminBadge />}
              </button>
            ))}
          </div>
        </div>
        {/* Fade-Gradient rechts — nur mobile */}
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
      </div>

      {/* Tab Content */}
      <div className="min-w-0">
        {activeTab === 'cpu' && <CpuTab timeRange={timeRange} />}
        {activeTab === 'memory' && <MemoryTab timeRange={timeRange} />}
        {activeTab === 'network' && <NetworkTab timeRange={timeRange} />}
        {activeTab === 'disk-io' && <DiskIoTab timeRange={timeRange} />}
        {activeTab === 'power' && <PowerTab />}
        {activeTab === 'services' && <ServicesStatusTab isAdmin={isAdmin} />}
        {activeTab === 'health' && <HealthTab />}
        {activeTab === 'logs' && <LogsTab />}
        {activeTab === 'activity' && <ActivityTab user={user} />}
      </div>
    </div>
  );
}
