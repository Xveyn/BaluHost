import { useMemo, useEffect, useState } from 'react';
import { useSystemTelemetry } from '../hooks/useSystemTelemetry';
import { useSmartData } from '../hooks/useSmartData';
import { getRaidStatus, type RaidStatusResponse } from '../api/raid';

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

const formatBytes = (bytes: number): string => {
  if (!bytes || Number.isNaN(bytes)) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(value >= 100 || value < 10 ? 1 : 2)} ${units[i]}`;
};

const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
};

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

export default function Dashboard() {
  const { system: systemInfo, storage: storageInfo, loading, error, lastUpdated, history } = useSystemTelemetry();
  const { smartData, loading: smartLoading, error: smartError } = useSmartData();
  const cachedRaid = getCachedRaid();
  const [raidData, setRaidData] = useState<RaidStatusResponse | null>(cachedRaid);
  const [raidLoading, setRaidLoading] = useState(!cachedRaid);

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

  const systemStats = useMemo<SystemStats>(() => {
    const cpuUsage = Math.max(0, Math.min(systemInfo?.cpu.usage ?? 0, 100));
    const cpuCores = systemInfo?.cpu.cores ?? 0;
    const memoryUsed = systemInfo?.memory.used ?? 0;
    const memoryTotal = systemInfo?.memory.total ?? 0;
    const uptime = systemInfo?.uptime ?? 0;

    return { cpuUsage, cpuCores, memoryUsed, memoryTotal, uptime };
  }, [systemInfo]);

  const storageStats = useMemo<StorageStats>(() => {
    // Berechne Gesamtkapazität und Nutzung aus SMART-Daten (alle Festplatten)
    let total = 0;
    let used = 0;
    
    if (smartData && smartData.devices.length > 0) {
      // Summiere alle Festplatten-Kapazitäten
      total = smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);
      
      // Summiere alle genutzten Bytes (falls vorhanden)
      used = smartData.devices.reduce((sum, d) => sum + (d.used_bytes || 0), 0);
      
      // Fallback: Wenn keine used_bytes vorhanden, verwende storageInfo
      if (used === 0 && storageInfo?.used) {
        used = storageInfo.used;
      }
    } else {
      // Fallback auf storageInfo wenn keine SMART-Daten vorhanden
      used = storageInfo?.used ?? 0;
      total = storageInfo?.total ?? 0;
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

  const quickStats = [
    {
      id: 'cpu',
      title: 'CPU Usage',
      value: `${systemStats.cpuUsage.toFixed(1)}%`,
      meta: `${systemStats.cpuCores || 0} cores active`,
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
      title: 'Memory',
      value: formatBytes(systemStats.memoryUsed),
      meta: `of ${formatBytes(systemStats.memoryTotal)}`,
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
      title: 'Total Storage',
      value: formatBytes(storageStats.used),
      meta: storageStats.total ? `of ${formatBytes(storageStats.total)} used` : 'Awaiting mount info',
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
      title: 'Uptime',
      value: formatUptime(systemStats.uptime),
      meta: 'System availability',
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

  const activityFeed = [
    {
      title: 'Backup Completed',
      detail: 'System image stored to NAS pool',
      ago: '2 minutes ago',
      icon: '⬇'
    },
    {
      title: 'Upload Finished',
      detail: 'Camera roll synced • family/photos',
      ago: '15 minutes ago',
      icon: '☁'
    },
    {
      title: 'New User Added',
      detail: 'sarah@baluhost.local granted access',
      ago: '1 hour ago',
      icon: '👤'
    }
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-white">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">Secure personal cloud orchestration overview</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className={`inline-flex h-2 w-2 rounded-full ${lastUpdated ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
          {lastUpdated ? `Synced ${lastUpdated.toLocaleTimeString()}` : 'Waiting for telemetry'}
        </div>
      </div>

      {error && (
        <div className="card border-rose-500/30 bg-rose-500/10 text-sm text-rose-100">
          {error}
        </div>
      )}

      {loading ? (
        <div className="card">
          <p className="text-sm text-slate-500">Loading system insights...</p>
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

              return (
                <div key={stat.id} className="card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)]">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{stat.title}</p>
                    <p className="mt-3 text-3xl font-semibold text-white">{stat.value}</p>
                  </div>
                  <div className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${stat.accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
                    {stat.icon}
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
                  <span>{stat.meta}</span>
                  <span className={deltaToneClass}>{stat.delta.label}</span>
                </div>
                <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${stat.accent}`}
                    style={{ width: `${Math.min(Math.max(stat.progress, 0), 100)}%` }}
                  />
                </div>
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 gap-6">
            <div className="card border-slate-800/50 bg-slate-900/55">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-500">Physical Drives</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">SMART Status</h2>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  {smartLoading ? (
                    <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-400">Loading...</span>
                  ) : smartError ? (
                    <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1 text-rose-200">Error</span>
                  ) : (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200">Healthy</span>
                  )}
                </div>
              </div>
              <div className="mt-6">
                {smartLoading ? (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
                    SMART-Daten werden geladen...
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
                      // berechne proportional basierend auf Gesamtspeicher
                      if (usedBytes === 0 && storageStats.used > 0) {
                        const totalHardwareCapacity = smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);
                        const deviceCapacity = device.capacity_bytes || 0;
                        
                        if (deviceCapacity > 0 && totalHardwareCapacity > 0) {
                          const deviceShare = deviceCapacity / totalHardwareCapacity;
                          usedBytes = Math.round(storageStats.used * deviceShare);
                          usagePercent = (usedBytes / deviceCapacity) * 100;
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
                                  <p className="text-slate-500">Status</p>
                                  <p className={`mt-1 font-medium ${device.status === 'PASSED' ? 'text-emerald-300' : 'text-rose-300'}`}>
                                    {device.status}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-slate-500">Kapazität</p>
                                  <p className="mt-1 font-medium text-slate-200">
                                    {device.capacity_bytes ? formatBytes(device.capacity_bytes) : 'N/A'}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-slate-500">Temperatur</p>
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
                            <div className="flex flex-col items-center justify-center">
                              <div className="relative flex h-20 w-20 items-center justify-center">
                                <div className="glow-ring h-20 w-20">
                                  <div className="absolute inset-1 rounded-full border border-slate-900/80 bg-slate-950/80" />
                                  <div className="glow-ring h-16 w-16 border-none" style={circleStyle}>
                                    <div className="h-12 w-12 rounded-full bg-slate-950/90" />
                                  </div>
                                </div>
                                <div className="absolute text-center">
                                  <p className="text-base font-semibold text-white">{Math.round(usagePercent)}%</p>
                                  <p className="text-[0.55rem] text-slate-400">{formatBytes(usedBytes)}</p>
                                </div>
                              </div>
                              <p className="mt-1 text-[0.65rem] text-slate-500">Genutzt</p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
                    Keine Festplatten gefunden
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[2fr_1fr]">
            <div className="card border-slate-800/50 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Recent Activity</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">Live operations</h2>
                </div>
                <button className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white">
                  View system logs
                </button>
              </div>
              <div className="mt-6 space-y-4">
                {activityFeed.map((item) => (
                  <div key={item.title} className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 transition hover:border-sky-500/30">
                    <div className="flex items-center gap-4">
                      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950/70 text-lg">
                        {item.icon}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-100">{item.title}</p>
                        <p className="text-xs text-slate-500">{item.detail}</p>
                      </div>
                    </div>
                    <span className="text-xs text-slate-500">{item.ago}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-6">
              <div className="card border-slate-800/50 bg-slate-900/55">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">NAS Configuration</p>
                <h3 className="mt-2 text-lg font-semibold text-white">RAID Arrays</h3>
                {raidLoading ? (
                  <div className="mt-5 text-sm text-slate-500">RAID-Daten werden geladen...</div>
                ) : raidData && raidData.arrays.length > 0 ? (
                  <div className="mt-5 space-y-3">
                    {raidData.arrays.map((array) => (
                      <div key={array.name} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-slate-100">{array.name}</p>
                            <p className="text-xs text-slate-500">RAID {array.level} • {(array.size_bytes / (1024 ** 3)).toFixed(1)} GB</p>
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${
                            array.status === 'clean' 
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                              : array.status.includes('degraded')
                              ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                              : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                          }`}>
                            {array.status}
                          </span>
                        </div>
                        <div className="mt-2 text-xs text-slate-400">
                          {array.devices.length} Geräte • {array.devices.filter(d => d.state.includes('active')).length} aktiv
                        </div>
                        {array.resync_progress !== null && array.resync_progress !== undefined && (
                          <div className="mt-2">
                            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                              <span>Resync Progress</span>
                              <span>{array.resync_progress.toFixed(1)}%</span>
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
                  <div className="mt-5 text-sm text-slate-500">Keine RAID-Arrays konfiguriert</div>
                )}
              </div>

              <div className="card border-slate-800/50 bg-slate-900/55">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">System Health</p>
                <h3 className="mt-2 text-lg font-semibold text-white">NAS Checks</h3>
                <ul className="mt-5 space-y-3 text-sm text-slate-400">
                  <li className="flex items-center justify-between">
                    <span>SMART Status</span>
                    {smartLoading ? (
                      <span className="text-slate-400">Prüfe...</span>
                    ) : smartError ? (
                      <span className="text-rose-300">Fehler</span>
                    ) : smartData && smartData.devices.every(d => d.status === 'PASSED') ? (
                      <span className="text-emerald-300">Alle Festplatten OK</span>
                    ) : (
                      <span className="text-amber-300">Warnung erkannt</span>
                    )}
                  </li>
                  <li className="flex items-center justify-between">
                    <span>RAID Status</span>
                    {raidLoading ? (
                      <span className="text-slate-400">Prüfe...</span>
                    ) : raidData && raidData.arrays.every(a => a.status === 'clean') ? (
                      <span className="text-emerald-300">Arrays optimal</span>
                    ) : raidData && raidData.arrays.some(a => a.status.includes('degraded')) ? (
                      <span className="text-amber-300">Degraded</span>
                    ) : (
                      <span className="text-slate-400">Kein RAID</span>
                    )}
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Physische Festplatten</span>
                    <span className="text-slate-200">
                      {smartData ? `${smartData.devices.length} erkannt` : '—'}
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Gesamtkapazität (HW)</span>
                    <span className="text-slate-200">
                      {smartData && smartData.devices.length > 0
                        ? formatBytes(smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0))
                        : '—'
                      }
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Durchschnitts-Temp</span>
                    <span className="text-slate-200">
                      {smartData && smartData.devices.length > 0 
                        ? `${Math.round(smartData.devices.reduce((sum, d) => sum + (d.temperature || 0), 0) / smartData.devices.length)}°C`
                        : '—'
                      }
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Speicher genutzt (FS)</span>
                    <span className="text-slate-200">{storageStats.percent.toFixed(1)}%</span>
                  </li>
                </ul>
              </div>

              <div className="card border-slate-800/50 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
                <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Next Maintenance</p>
                <h3 className="mt-2 text-lg font-semibold text-white">Scheduled raid scrub</h3>
                <p className="mt-3 text-sm text-slate-400">Automated integrity check for pool alpha is planned for 03:00 UTC.</p>
                <div className="mt-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Window</p>
                    <p className="mt-1 text-sm text-slate-200">Saturday - 26 Oct - 02:30 - 03:30</p>
                  </div>
                  <button className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white">
                    View plan
                  </button>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
