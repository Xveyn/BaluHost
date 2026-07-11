import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { useSystemTelemetry } from '../hooks/useSystemTelemetry';
import { useSmartData } from '../hooks/useSmartData';
import { useGpuPresence } from '../hooks/useGpuPresence';
import { useGpuCurrent } from '../hooks/useGpuCurrent';
import { useRaidStatus } from '../hooks/useRaidStatus';
import { useSmartMode } from '../hooks/useSmartMode';
import { useNextMaintenance } from '../hooks/useNextMaintenance';
import { useServicesSummary } from '../hooks/useServicesSummary';
import { useLiveActivities } from '../hooks/useLiveActivities';
import { useDashboardStats } from '../hooks/useDashboardStats';
import { useDashboardAlerts } from '../hooks/useDashboardAlerts';
import {
  ActivityFeed,
  NextMaintenanceWidget,
  ServicesPanel,
  PluginsPanel,
  NetworkWidget,
  ConnectedDevicesWidget,
  AlertBanner,
  LiveActivities,
  PluginDashboardPanel,
  CpuGpuPanel,
  QuickStatCard,
  SmartHealthPanel,
  RaidSummaryCard,
  SystemHealthCard,
  type QuickStat,
} from '../components/dashboard';
import { detectGpuVendor } from '../components/dashboard/CpuGpuPanel';
import { cpuIcon, memoryIcon, storageIcon, uptimeIcon } from '../components/dashboard/statIcons';
import { formatBytes, formatUptime, formatNumber } from '../lib/formatters';

export default function Dashboard() {
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');
  const { isAdmin } = useAuth();
  const { system: systemInfo, storage: storageInfo, loading, error, lastUpdated, history } = useSystemTelemetry();

  const { smartData, loading: smartLoading, error: smartError } = useSmartData();
  const { raidData, raidLoading } = useRaidStatus();
  // Dev-only SMART data source toggle (mock↔real) — query-backed (#299): shares
  // the system/smart mode cache with MaintenancePanel; toggle refreshes the
  // SMART disk data via smart.status() invalidation.
  const { smartMode, toggle: handleToggleSmartMode, isToggling: smartModeLoading } = useSmartMode();

  // GPU presence + polling — shared `gpu.current` query (#299), gated on presence
  const { present: hasGpu, info: gpuInfo } = useGpuPresence();
  const gpuSample = useGpuCurrent(hasGpu);

  // Hooks for alert generation
  const { allSchedulers } = useNextMaintenance();
  const { services } = useServicesSummary({ enabled: isAdmin });
  const { activities } = useLiveActivities({ raidData, schedulers: allSchedulers, isAdmin });

  // Derived stat cards + alerts (extracted F2/#301)
  const stats = useDashboardStats({ systemInfo, storageInfo, smartData, history });
  const alerts = useDashboardAlerts({ smartData, raidData, allSchedulers, services, isAdmin });

  const quickStats: QuickStat[] = [
    // When a dedicated GPU is detected, the CPU card is replaced by the
    // combined CpuGpuPanel rendered alongside this list. Otherwise show CPU here.
    ...(hasGpu ? [] : [{
      id: 'cpu',
      title: t('stats.cpu'),
      value: `${formatNumber(stats.cpuStatBase.usagePercent, 1)}%`,
      meta: stats.cpuStatBase.meta,
      submeta: stats.cpuStatBase.submeta,
      delta: stats.cpuStatBase.delta,
      accent: 'from-violet-500 to-fuchsia-500',
      progress: stats.cpuStatBase.usagePercent,
      icon: cpuIcon,
    }]),
    {
      id: 'memory',
      title: t('stats.memory'),
      value: formatBytes(stats.systemStats.memoryUsed),
      meta: stats.memorySpeedType || t('stats.ofTotal', { total: formatBytes(stats.systemStats.memoryTotal) }),
      submeta: stats.memorySpeedType ? t('stats.ofTotal', { total: formatBytes(stats.systemStats.memoryTotal) }) : undefined,
      delta: stats.memoryDelta,
      accent: 'from-sky-500 to-indigo-500',
      progress: stats.memoryPercent,
      icon: memoryIcon,
    },
    {
      id: 'storage',
      title: t('stats.totalStorage'),
      value: formatBytes(stats.storageStats.used),
      meta: stats.storageStats.total ? t('stats.ofTotal', { total: formatBytes(stats.storageStats.total) }) : t('stats.awaitingMount'),
      delta: stats.storageDelta,
      accent: 'from-cyan-500 to-sky-600',
      progress: stats.storageStats.percent,
      icon: storageIcon,
    },
    {
      id: 'uptime',
      title: t('stats.serverUptime'),
      value: formatUptime(stats.systemStats.uptime),
      meta: t('stats.systemUptimeLabel', { uptime: formatUptime(stats.systemStats.systemUptime) }),
      delta: { label: 'Live', tone: 'live' },
      accent: 'from-emerald-500 to-teal-500',
      progress: 100,
      icon: uptimeIcon,
    },
  ];

  const handlerFor = (id: string): (() => void) | undefined => {
    switch (id) {
      case 'cpu': return () => navigate('/system?tab=cpu');
      case 'memory': return () => navigate('/system?tab=memory');
      case 'storage': return () => navigate('/system?tab=disk-io');
      case 'uptime': return () => navigate('/system?tab=uptime');
      default: return undefined;
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-sm text-slate-400">{t('subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className={`inline-flex h-2 w-2 rounded-full ${lastUpdated ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
          {lastUpdated ? t('sync.synced', { time: lastUpdated.toLocaleTimeString() }) : t('sync.waiting')}
        </div>
      </div>

      {/* Alert Banner */}
      {alerts.length > 0 && <AlertBanner alerts={alerts} />}

      {error && (
        <div className="card border-rose-500/30 bg-rose-500/10 text-sm text-rose-100">
          {error}
        </div>
      )}

      {loading ? (
        <div className="card">
          <p className="text-sm text-slate-500">{t('loading')}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {hasGpu && gpuInfo && (
              <CpuGpuPanel
                cpu={stats.cpuStatBase}
                gpu={{ vendor: detectGpuVendor(gpuInfo.vendor), info: gpuInfo, sample: gpuSample }}
              />
            )}
            {quickStats.map((stat) => (
              <QuickStatCard key={stat.id} stat={stat} onClick={handlerFor(stat.id)} />
            ))}

            {/* Plugin Dashboard Panel */}
            <PluginDashboardPanel />

            {/* Network Widget */}
            <NetworkWidget />

            {/* Services Panel (visible to all, clickable for admins) */}
            <ServicesPanel isAdmin={isAdmin} />

            {/* Plugins Panel (visible to all, clickable for admins) */}
            <PluginsPanel isAdmin={isAdmin} />
          </div>

          {/* Live Activities - below panels */}
          {activities.length > 0 && <LiveActivities activities={activities} />}

          <SmartHealthPanel
            smartData={smartData}
            smartLoading={smartLoading}
            smartError={smartError}
            smartMode={smartMode}
            smartModeLoading={smartModeLoading}
            onToggleSmartMode={handleToggleSmartMode}
            storageUsed={stats.storageStats.used}
          />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[2fr_1fr]">
            {/* Activity Feed - Now with real data */}
            <ActivityFeed limit={5} />

            <div className="space-y-6">
              <RaidSummaryCard raidData={raidData} raidLoading={raidLoading} />

              <SystemHealthCard
                smartData={smartData}
                smartLoading={smartLoading}
                smartError={smartError}
                raidData={raidData}
                raidLoading={raidLoading}
                storagePercent={stats.storageStats.percent}
              />

              {/* Connected Devices Widget */}
              <ConnectedDevicesWidget />

              {/* Next Maintenance Widget - Now with real scheduler data */}
              <NextMaintenanceWidget showAllSchedulers={isAdmin} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
