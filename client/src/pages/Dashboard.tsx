import { useMemo, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useSystemTelemetry } from '../hooks/useSystemTelemetry';
import { useSmartData } from '../hooks/useSmartData';
import { getRaidStatus, type RaidStatusResponse } from '../api/raid';
import { useNextMaintenance } from '../hooks/useNextMaintenance';
import { useServicesSummary } from '../hooks/useServicesSummary';
import { useLiveActivities } from '../hooks/useLiveActivities';
import PowerWidget from '../components/PowerWidget';
import {
  ActivityFeed,
  NextMaintenanceWidget,
  ServicesPanel,
  PluginsPanel,
  NetworkWidget,
  ConnectedDevicesWidget,
  AlertBanner,
  LiveActivities,
  type Alert,
} from '../components/dashboard';
import { formatBytes, formatUptime, formatNumber } from '../lib/formatters';

interface SystemStats {
  cpuUsage: number;
  cpuCores: number;
  memoryUsed: number;
  memoryTotal: number;
  uptime: number;
}

interface StorageStats {
  used: number;
  total: number;
  available: number;
  percent: number;
}

interface DashboardProps {
  user?: {
    role: string;
  };
}

const RAID_CACHE_KEY = 'raid_status_cache';
const RAID_CACHE_DURATION = 120000; // 2 minutes

function getCachedRaid(): RaidStatusResponse | null {
  try {
    const cached = sessionStorage.getItem(RAID_CACHE_KEY);
    if (cached) {
      const data = JSON.parse(cached);
      const age = Date.now() - (data.timestamp || 0);
      if (age < RAID_CACHE_DURATION) {
        return data.raid;
      }
    }
  } catch (err) {
    console.error('Failed to read RAID cache:', err);
  }
  return null;
}

function setCachedRaid(raid: RaidStatusResponse): void {
  try {
    sessionStorage.setItem(RAID_CACHE_KEY, JSON.stringify({
      raid,
      timestamp: Date.now()
    }));
  } catch (err) {
    console.error('Failed to write RAID cache:', err);
  }
}

export default function Dashboard({ user }: DashboardProps) {
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');
  const isAdmin = user?.role === 'admin';
  const { system: systemInfo, storage: storageInfo, loading, error, lastUpdated, history } = useSystemTelemetry();

  // Navigation handlers for dashboard panels
  const handleCpuClick = () => navigate('/system?tab=cpu');
  const handleMemoryClick = () => navigate('/system?tab=memory');
  const handleStorageClick = () => navigate('/system?tab=disk-io');
  const { smartData, loading: smartLoading, error: smartError, refetch: refetchSmartData } = useSmartData();
  const cachedRaid = getCachedRaid();
  const [raidData, setRaidData] = useState<RaidStatusResponse | null>(cachedRaid);
  const [raidLoading, setRaidLoading] = useState(!cachedRaid);
  const [smartMode, setSmartMode] = useState<string | null>(null);
  const [smartModeLoading, setSmartModeLoading] = useState(false);

  // Hooks for alert generation
  const { allSchedulers } = useNextMaintenance({ enabled: isAdmin });
  const { services } = useServicesSummary({ enabled: isAdmin });
  const { activities } = useLiveActivities({ raidData, schedulers: allSchedulers, isAdmin });

  useEffect(() => {
    const loadRaidData = async () => {
      try {
        const data = await getRaidStatus();
        setRaidData(data);
        setCachedRaid(data);
      } catch (err) {
        console.error('RAID-Daten konnten nicht geladen werden:', err);
      } finally {
        setRaidLoading(false);
      }
    };

    loadRaidData();
    const interval = setInterval(loadRaidData, 60000); // Poll every 60 seconds

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const loadSmartMode = async () => {
      try {
        const modeRes = await fetch('/api/system/mode');
        const modeData = await modeRes.json();
        if (!modeData?.dev_mode) return;

        const { getSmartMode } = await import('../api/smart');
        const response = await getSmartMode();
        setSmartMode(response.mode);
      } catch (err) {
        console.debug('SMART mode toggle not available:', err);
      }
    };

    loadSmartMode();
  }, []);

  const handleToggleSmartMode = async () => {
    setSmartModeLoading(true);
    try {
      const { toggleSmartMode } = await import('../api/smart');
      const response = await toggleSmartMode();
      setSmartMode(response.mode);
      refetchSmartData();
    } catch (err) {
      console.error('Failed to toggle SMART mode:', err);
    } finally {
      setSmartModeLoading(false);
    }
  };

  const systemStats = useMemo<SystemStats>(() => {
    const cpuUsage = Math.max(0, Math.min(systemInfo?.cpu.usage ?? 0, 100));
    const cpuCores = systemInfo?.cpu.cores ?? 0;
    const memoryUsed = systemInfo?.memory.used ?? 0;
    const memoryTotal = systemInfo?.memory.total ?? 0;
    const uptime = systemInfo?.uptime ?? 0;

    return { cpuUsage, cpuCores, memoryUsed, memoryTotal, uptime };
  }, [systemInfo]);

  const storageStats = useMemo<StorageStats>(() => {
    let total = 0;
    let used = 0;

    if (storageInfo && storageInfo.total > 0) {
      // Primär: Aggregierte Daten (berücksichtigt RAID-effektive Kapazität)
      total = storageInfo.total;
      used = storageInfo.used;
    } else if (smartData && smartData.devices.length > 0) {
      // Fallback: SMART-Daten summieren
      total = smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);
      used = smartData.devices.reduce((sum, d) => sum + (d.used_bytes || 0), 0);
    }

    const available = Math.max(total - used, 0);
    const percent = total ? (used / total) * 100 : 0;

    return {
      used,
      total,
      available,
      percent: Math.min(Math.max(percent, 0), 100)
    };
  }, [storageInfo, smartData]);

  const memoryPercent = useMemo(() => {
    return systemStats.memoryTotal ? (systemStats.memoryUsed / systemStats.memoryTotal) * 100 : 0;
  }, [systemStats.memoryTotal, systemStats.memoryUsed]);

  const cpuDelta = useMemo(() => {
    const points = history.cpu;
    if (points.length < 2) {
      return null;
    }
    const latest = points[points.length - 1]?.usage ?? 0;
    const previous = points[points.length - 2]?.usage ?? latest;
    return latest - previous;
  }, [history.cpu]);

  const memoryDelta = useMemo(() => {
    const points = history.memory;
    if (points.length < 2) {
      return null;
    }
    const latest = points[points.length - 1]?.percent ?? 0;
    const previous = points[points.length - 2]?.percent ?? latest;
    return latest - previous;
  }, [history.memory]);

  const storageDelta = null;

  type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';

  const formatDelta = (value: number | null, suffix = '%'): { label: string; tone: DeltaTone } => {
    if (value === null) {
      return { label: 'Live', tone: 'live' };
    }
    const rounded = Number(value.toFixed(1));
    if (rounded === 0) {
      return { label: `0${suffix}`, tone: 'steady' };
    }
    if (rounded > 0) {
      return { label: `+${rounded}${suffix}`, tone: 'increase' };
    }
    return { label: `${rounded}${suffix}`, tone: 'decrease' };
  };

  const cpuFrequency = useMemo(() => {
    return systemInfo?.cpu?.frequency_mhz
      ? `${formatNumber(systemInfo.cpu.frequency_mhz / 1000, 2)} GHz`
      : null;
  }, [systemInfo]);

  const cpuTemperature = useMemo(() => {
    const t = systemInfo?.cpu?.temperature_celsius;
    return typeof t === 'number' ? `${formatNumber(t, 1)}°C` : null;
  }, [systemInfo]);

  const cpuModel = useMemo(() => {
    return systemInfo?.cpu?.model || null;
  }, [systemInfo]);

  const memorySpeedType = useMemo(() => {
    const speed = systemInfo?.memory?.speed_mts;
    const type = systemInfo?.memory?.type;

    if (speed && type) {
      return `${type} @ ${speed} MT/s`;
    } else if (type) {
      return type;
    } else if (speed) {
      return `${speed} MT/s`;
    }
    return null;
  }, [systemInfo]);

  // Generate alerts from various sources
  const alerts = useMemo<Alert[]>(() => {
    const result: Alert[] = [];

    // SMART alerts — split FAILED (critical) vs UNKNOWN (warning)
    if (smartData) {
      const failedDevices = smartData.devices.filter(d => d.status === 'FAILED');
      const unknownDevices = smartData.devices.filter(d => d.status === 'UNKNOWN');
      if (failedDevices.length > 0) {
        result.push({
          id: 'smart-failure',
          type: 'critical',
          title: t('alerts.smartFailure.title'),
          message: t('alerts.smartFailure.message', { count: failedDevices.length }),
          link: '/system',
          linkText: t('alerts.viewDetails'),
          source: 'smart',
        });
      }
      if (unknownDevices.length > 0) {
        result.push({
          id: 'smart-unknown',
          type: 'warning',
          title: t('alerts.smartUnknown.title'),
          message: t('alerts.smartUnknown.message', { count: unknownDevices.length }),
          link: '/system',
          linkText: t('alerts.viewDetails'),
          source: 'smart',
        });
      }
    }

    // RAID alerts
    if (raidData && raidData.arrays.some(a => a.status.includes('degraded'))) {
      const degradedArrays = raidData.arrays.filter(a => a.status.includes('degraded'));
      result.push({
        id: 'raid-degraded',
        type: 'critical',
        title: t('alerts.raidDegraded.title'),
        message: t('alerts.raidDegraded.message', { count: degradedArrays.length }),
        link: '/raid',
        linkText: t('alerts.viewRaid'),
        source: 'raid',
      });
    }

    // Scheduler alerts (only for admin)
    if (isAdmin && allSchedulers.some(s => s.last_status === 'failed')) {
      const failedSchedulers = allSchedulers.filter(s => s.last_status === 'failed');
      result.push({
        id: 'scheduler-failed',
        type: 'warning',
        title: t('alerts.schedulerFailed.title'),
        message: t('alerts.schedulerFailed.message', { count: failedSchedulers.length }),
        link: '/schedulers',
        linkText: t('alerts.viewSchedulers'),
        source: 'scheduler',
      });
    }

    // Service alerts (only for admin)
    if (isAdmin && services.some(s => s.state === 'error')) {
      const errorServices = services.filter(s => s.state === 'error');
      result.push({
        id: 'service-error',
        type: 'warning',
        title: t('alerts.serviceError.title'),
        message: t('alerts.serviceError.message', { count: errorServices.length }),
        link: '/health',
        linkText: t('alerts.viewHealth'),
        source: 'service',
      });
    }

    return result;
  }, [smartData, raidData, allSchedulers, services, isAdmin, t]);

  const quickStats = [
    {
      id: 'cpu',
      title: t('stats.cpu'),
      value: `${formatNumber(systemStats.cpuUsage, 1)}%`,
      meta: cpuModel
        ? cpuModel
        : (cpuFrequency
          ? t('stats.coresAt', { count: systemStats.cpuCores || 0, frequency: cpuFrequency }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')
          : t('stats.coresActive', { count: systemStats.cpuCores || 0 }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')),
      submeta: cpuModel && cpuFrequency
        ? t('stats.coresAt', { count: systemStats.cpuCores || 0, frequency: cpuFrequency }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')
        : undefined,
      delta: formatDelta(cpuDelta),
      accent: 'from-violet-500 to-fuchsia-500',
      progress: systemStats.cpuUsage,
      icon: (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H6.75A1.5 1.5 0 005.25 6v12a1.5 1.5 0 001.5 1.5z" />
        </svg>
      )
    },
    {
      id: 'memory',
      title: t('stats.memory'),
      value: formatBytes(systemStats.memoryUsed),
      meta: memorySpeedType || t('stats.ofTotal', { total: formatBytes(systemStats.memoryTotal) }),
      submeta: memorySpeedType ? t('stats.ofTotal', { total: formatBytes(systemStats.memoryTotal) }) : undefined,
      delta: formatDelta(memoryDelta),
      accent: 'from-sky-500 to-indigo-500',
      progress: memoryPercent,
      icon: (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 5.25h16.5m-16.5 4.5h16.5m-16.5 4.5h16.5m-16.5 4.5h16.5M6 3v18m6-18v18m6-18v18" />
        </svg>
      )
    },
    {
      id: 'storage',
      title: t('stats.totalStorage'),
      value: formatBytes(storageStats.used),
      meta: storageStats.total ? t('stats.ofTotal', { total: formatBytes(storageStats.total) }) : t('stats.awaitingMount'),
      delta: formatDelta(storageDelta),
      accent: 'from-cyan-500 to-sky-600',
      progress: storageStats.percent,
      icon: (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859M12 3v8.25m0 0l-3-3m3 3l3-3" />
        </svg>
      )
    },
    {
      id: 'uptime',
      title: t('stats.uptime'),
      value: formatUptime(systemStats.uptime),
      meta: t('stats.systemAvailability'),
      delta: { label: 'Live', tone: 'live' },
      accent: 'from-emerald-500 to-teal-500',
      progress: 100,
      icon: (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
        </svg>
      )
    }
  ];

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
            {quickStats.map((stat) => {
              const deltaToneClass = stat.delta.tone === 'decrease'
                ? 'text-emerald-400'
                : stat.delta.tone === 'increase'
                  ? 'text-rose-300'
                  : stat.delta.tone === 'steady'
                    ? 'text-slate-400'
                    : 'text-sky-400';

              // Click handler based on stat ID
              const handleClick = stat.id === 'cpu' ? handleCpuClick
                : stat.id === 'memory' ? handleMemoryClick
                : stat.id === 'storage' ? handleStorageClick
                : undefined;

              const isClickable = !!handleClick;

              return (
                <div
                  key={stat.id}
                  onClick={handleClick}
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
            })}

            {/* Power Monitoring Widget */}
            <PowerWidget />

            {/* Network Widget */}
            <NetworkWidget />

            {/* Services Panel (visible to all, clickable for admins) */}
            <ServicesPanel isAdmin={isAdmin} />

            {/* Plugins Panel (visible to all, clickable for admins) */}
            <PluginsPanel isAdmin={isAdmin} />
          </div>

          {/* Live Activities - below panels */}
          {activities.length > 0 && <LiveActivities activities={activities} />}

          <div className="grid grid-cols-1 gap-6">
            <div className="card border-slate-800/50 bg-slate-900/55">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-500">{t('smart.title')}</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">{t('smart.subtitle')}</h2>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  {smartMode && (
                    <button
                      onClick={handleToggleSmartMode}
                      disabled={smartModeLoading}
                      className="rounded-full border border-slate-700/70 bg-slate-800/50 px-3 py-1 text-slate-300 transition hover:border-sky-500/50 hover:bg-slate-700/50 hover:text-white disabled:opacity-50"
                      title={t('smart.modeToggle.current', { mode: smartMode === 'mock' ? t('smart.modeToggle.mock') : t('smart.modeToggle.real') })}
                    >
                      {smartModeLoading ? '...' : (smartMode === 'mock' ? '🔄 Mock' : '🔄 Real')}
                    </button>
                  )}
                  {smartLoading ? (
                    <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-400">{t('network.loading')}</span>
                  ) : smartError ? (
                    <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1 text-rose-200">{t('smart.error')}</span>
                  ) : (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200">{t('smart.healthy')}</span>
                  )}
                </div>
              </div>
              <div className="mt-6">
                {smartLoading ? (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
                    {t('smart.loading')}
                  </div>
                ) : smartError ? (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-rose-500/30 bg-rose-500/10 text-sm text-rose-200">
                    {smartError}
                  </div>
                ) : smartData && smartData.devices.length > 0 ? (
                  <div className="space-y-3">
                    {smartData.devices.map((device) => {
                      const criticalAttributes = device.attributes.filter(attr =>
                        ['Reallocated_Sector_Ct', 'Current_Pending_Sector', 'Uncorrectable_Error_Cnt'].includes(attr.name)
                      );
                      const tempAttr = device.attributes.find(attr => attr.name === 'Temperature_Celsius');

                      // Verwende die tatsächlichen Nutzungsdaten vom Backend, falls verfügbar
                      let usagePercent = device.used_percent ?? 0;
                      let usedBytes = device.used_bytes ?? 0;

                      // Fallback: Wenn keine direkten Nutzungsdaten verfügbar sind,
                      // berechne basierend auf RAID-Membership oder proportional
                      if (usedBytes === 0 && storageStats.used > 0) {
                        const deviceCapacity = device.capacity_bytes || 0;

                        if (device.raid_member_of && deviceCapacity > 0) {
                          // RAID-Member: Jede Disk enthält alle Daten (RAID 1 = volle Spiegelung)
                          usedBytes = storageStats.used;
                          usagePercent = (usedBytes / deviceCapacity) * 100;
                        } else if (deviceCapacity > 0) {
                          // Non-RAID: Proportionale Verteilung über non-RAID Devices
                          const nonRaidCapacity = smartData.devices
                            .filter(d => !d.raid_member_of)
                            .reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);

                          if (nonRaidCapacity > 0) {
                            const deviceShare = deviceCapacity / nonRaidCapacity;
                            usedBytes = Math.round(storageStats.used * deviceShare);
                            usagePercent = (usedBytes / deviceCapacity) * 100;
                          }
                        }
                      }

                      const circleStyle = {
                        backgroundImage: `conic-gradient(#0ea5e9 ${Math.min(usagePercent, 100) * 3.6}deg, rgba(15,23,42,0.8) ${Math.min(usagePercent, 100) * 3.6}deg)`
                      };

                      return (
                        <div key={device.serial} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-sky-500/30">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1">
                              <div className="flex items-center gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70">
                                  <svg className="h-5 w-5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15" />
                                  </svg>
                                </div>
                                <div>
                                  <p className="text-sm font-medium text-slate-100">{device.model}</p>
                                  <p className="text-xs text-slate-500">{device.name} • {device.serial}</p>
                                </div>
                              </div>
                              <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                                <div>
                                  <p className="text-slate-500">{t('smart.device.status')}</p>
                                  <p className={`mt-1 font-medium ${device.status === 'PASSED' ? 'text-emerald-300' : device.status === 'UNKNOWN' ? 'text-amber-300' : 'text-rose-300'}`}>
                                    {device.status}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-slate-500">{t('smart.device.capacity')}</p>
                                  <p className="mt-1 font-medium text-slate-200">
                                    {device.capacity_bytes ? formatBytes(device.capacity_bytes) : 'N/A'}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-slate-500">{t('smart.device.temperature')}</p>
                                  <p className="mt-1 font-medium text-slate-200">
                                    {device.temperature !== null ? `${device.temperature}°C` : tempAttr ? `${tempAttr.raw}°C` : 'N/A'}
                                  </p>
                                </div>
                                {criticalAttributes.slice(0, 1).map(attr => (
                                  <div key={attr.id}>
                                    <p className="text-slate-500">{attr.name.replace(/_/g, ' ')}</p>
                                    <p className={`mt-1 font-medium ${attr.status === 'OK' ? 'text-emerald-300' : 'text-rose-300'}`}>
                                      {attr.raw} ({attr.status})
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="flex flex-col items-center justify-center flex-shrink-0">
                              <div className="relative flex h-16 w-16 sm:h-20 sm:w-20 items-center justify-center">
                                <div className="glow-ring h-16 w-16 sm:h-20 sm:w-20">
                                  <div className="absolute inset-1 rounded-full border border-slate-900/80 bg-slate-950/80" />
                                  <div className="glow-ring h-12 w-12 sm:h-16 sm:w-16 border-none" style={circleStyle}>
                                    <div className="h-8 w-8 sm:h-12 sm:w-12 rounded-full bg-slate-950/90" />
                                  </div>
                                </div>
                                <div className="absolute text-center">
                                  <p className="text-sm sm:text-base font-semibold text-white">{Math.round(usagePercent)}%</p>
                                  <p className="text-[0.5rem] sm:text-[0.55rem] text-slate-400">{formatBytes(usedBytes)}</p>
                                </div>
                              </div>
                              <p className="mt-1 text-[0.65rem] text-slate-500">{t('smart.device.used')}</p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
                    {t('smart.noDevices')}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[2fr_1fr]">
            {/* Activity Feed - Now with real data */}
            <ActivityFeed limit={5} />

            <div className="space-y-6">
              <div className="card border-slate-800/50 bg-slate-900/55">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('raid.configTitle')}</p>
                <h3 className="mt-2 text-lg font-semibold text-white">{t('raid.title')}</h3>
                {raidLoading ? (
                  <div className="mt-5 text-sm text-slate-500">{t('raid.loading')}</div>
                ) : raidData && raidData.arrays.length > 0 ? (
                  <div className="mt-5 space-y-3">
                    {raidData.arrays.map((array) => (
                      <div key={array.name} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-slate-100">{array.name}</p>
                            <p className="text-xs text-slate-500">RAID {array.level} • {formatNumber(array.size_bytes / (1024 ** 3), 1)} GB</p>
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${
                            array.status === 'clean' || array.status === 'optimal'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                              : array.status === 'checking'
                              ? 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300'
                              : array.status === 'rebuilding'
                              ? 'border-sky-500/30 bg-sky-500/10 text-sky-300'
                              : array.status.includes('degraded')
                              ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                              : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                          }`}>
                            {array.status}
                          </span>
                        </div>
                        <div className="mt-2 text-xs text-slate-400">
                          {t('raid.devices', { count: array.devices.length })} • {t('raid.active', { count: array.devices.filter(d => d.state.includes('active')).length })}
                        </div>
                        {array.resync_progress !== null && array.resync_progress !== undefined && (
                          <div className="mt-2">
                            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                              <span>{t('raid.resyncProgress')}</span>
                              <span>{formatNumber(array.resync_progress, 1)}%</span>
                            </div>
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
                                style={{ width: `${array.resync_progress}%` }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-5 text-sm text-slate-500">{t('raid.noArrays')}</div>
                )}
              </div>

              <div className="card border-slate-800/50 bg-slate-900/55">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('health.title')}</p>
                <h3 className="mt-2 text-lg font-semibold text-white">{t('health.checksTitle')}</h3>
                <ul className="mt-5 space-y-3 text-sm text-slate-400">
                  <li className="flex items-center justify-between">
                    <span>{t('smart.subtitle')}</span>
                    {smartLoading ? (
                      <span className="text-slate-400">{t('health.checking')}</span>
                    ) : smartError ? (
                      <span className="text-rose-300">{t('health.error')}</span>
                    ) : smartData && smartData.devices.every(d => d.status === 'PASSED') ? (
                      <span className="text-emerald-300">{t('health.allDrivesOk')}</span>
                    ) : (
                      <span className="text-amber-300">{t('health.warningDetected')}</span>
                    )}
                  </li>
                  <li className="flex items-center justify-between">
                    <span>{t('system.raidStatus')}</span>
                    {raidLoading ? (
                      <span className="text-slate-400">{t('health.checking')}</span>
                    ) : raidData && raidData.arrays.every(a => ['clean', 'optimal', 'checking'].includes(a.status)) ? (
                      <span className="text-emerald-300">{t('health.arraysOptimal')}</span>
                    ) : raidData && raidData.arrays.some(a => a.status.includes('degraded')) ? (
                      <span className="text-amber-300">{t('health.degraded')}</span>
                    ) : (
                      <span className="text-slate-400">{t('health.noRaid')}</span>
                    )}
                  </li>
                  <li className="flex items-center justify-between">
                    <span>{t('health.physicalDrives')}</span>
                    <span className="text-slate-200">
                      {smartData ? t('health.detected', { count: smartData.devices.length }) : '—'}
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>{t('health.totalCapacity')}</span>
                    <span className="text-slate-200">
                      {smartData && smartData.devices.length > 0
                        ? formatBytes(smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0))
                        : '—'
                      }
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>{t('health.avgTemp')}</span>
                    <span className="text-slate-200">
                      {smartData && smartData.devices.length > 0
                        ? `${Math.round(smartData.devices.reduce((sum, d) => sum + (d.temperature || 0), 0) / smartData.devices.length)}°C`
                        : '—'
                      }
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>{t('health.storageUsed')}</span>
                    <span className="text-slate-200">{formatNumber(storageStats.percent, 1)}%</span>
                  </li>
                </ul>
              </div>

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
