import { useMemo } from 'react';
import { useSystemTelemetry } from '../hooks/useSystemTelemetry';

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

interface ChartPath {
  line: string;
  area: string;
}

const buildChartPath = (series: number[], width = 280, height = 120): ChartPath => {
  if (!series.length) {
    return { line: '', area: '' };
  }

  const maxValue = Math.max(...series, 1);
  const step = series.length > 1 ? width / (series.length - 1) : width;

  // Builds a path string for the sparkline and its filled area.
  const coordinates = series
    .map((point, index) => {
      const x = index * step;
      const y = height - (point / maxValue) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');

  const area = `${coordinates} L ${width.toFixed(1)} ${height.toFixed(1)} L 0 ${height.toFixed(1)} Z`;
  return { line: coordinates, area };
};

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

export default function Dashboard() {
  const { system: systemInfo, storage: storageInfo, loading, error, lastUpdated, history } = useSystemTelemetry();

  const systemStats = useMemo<SystemStats>(() => {
    const cpuUsage = Math.max(0, Math.min(systemInfo?.cpu.usage ?? 0, 100));
    const cpuCores = systemInfo?.cpu.cores ?? 0;
    const memoryUsed = systemInfo?.memory.used ?? 0;
    const memoryTotal = systemInfo?.memory.total ?? 0;
    const uptime = systemInfo?.uptime ?? 0;

    return { cpuUsage, cpuCores, memoryUsed, memoryTotal, uptime };
  }, [systemInfo]);

  const storageStats = useMemo<StorageStats>(() => {
    const used = storageInfo?.used ?? 0;
    const total = storageInfo?.total ?? 0;
    const available = storageInfo?.available ?? Math.max(total - used, 0);
    const percent = storageInfo?.percent ?? (total ? (used / total) * 100 : 0);

    return {
      used,
      total,
      available,
      percent: Math.min(Math.max(percent, 0), 100)
    };
  }, [storageInfo]);

  const memoryPercent = useMemo(() => {
    return systemStats.memoryTotal ? (systemStats.memoryUsed / systemStats.memoryTotal) * 100 : 0;
  }, [systemStats.memoryTotal, systemStats.memoryUsed]);

  const latestNetworkTrail = useMemo(() => {
    return history.network.slice(-24);
  }, [history.network]);

  const downloadSeries = useMemo(() => {
    return latestNetworkTrail.map((point) => point.downloadMbps ?? 0);
  }, [latestNetworkTrail]);

  const uploadSeries = useMemo(() => {
    return latestNetworkTrail.map((point) => point.uploadMbps ?? 0);
  }, [latestNetworkTrail]);

  const downPaths = useMemo(() => buildChartPath(downloadSeries), [downloadSeries]);
  const upPaths = useMemo(() => buildChartPath(uploadSeries), [uploadSeries]);

  const networkSnapshot = useMemo(() => {
    const latestPoint = latestNetworkTrail[latestNetworkTrail.length - 1];
    return {
      down: latestPoint?.downloadMbps ?? 0,
      up: latestPoint?.uploadMbps ?? 0
    };
  }, [latestNetworkTrail]);

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
      accent: 'from-sky-500 to-indigo-500',
      progress: systemStats.cpuUsage
    },
    {
      id: 'memory',
      title: 'Memory',
      value: formatBytes(systemStats.memoryUsed),
      meta: `of ${formatBytes(systemStats.memoryTotal)}`,
      delta: formatDelta(memoryDelta),
      accent: 'from-violet-500 to-fuchsia-500',
      progress: memoryPercent
    },
    {
      id: 'storage',
      title: 'Storage',
      value: formatBytes(storageStats.used),
      meta: storageStats.total ? `of ${formatBytes(storageStats.total)}` : 'Awaiting mount info',
      delta: formatDelta(storageDelta),
      accent: 'from-cyan-500 to-sky-600',
      progress: storageStats.percent
    },
    {
      id: 'uptime',
      title: 'Uptime',
      value: formatUptime(systemStats.uptime),
      meta: 'System availability',
      delta: { label: 'Live', tone: 'live' },
      accent: 'from-emerald-500 to-teal-500',
      progress: 100
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

  const storageRingStyle = {
    backgroundImage: `conic-gradient(#38bdf8 ${storageStats.percent * 3.6}deg, rgba(15,23,42,0.8) ${storageStats.percent * 3.6}deg)`
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-white">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">Secure personal cloud orchestration overview</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400" />
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
                <div key={stat.id} className="card border-slate-800/40 bg-slate-900/60">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{stat.title}</p>
                    <p className="mt-3 text-3xl font-semibold text-white">{stat.value}</p>
                  </div>
                  <div className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${stat.accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
                    ●
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

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="card lg:col-span-2 border-slate-800/50 bg-slate-900/55">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-500">Network Activity</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">Traffic pulse</h2>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-sky-200">Live</span>
                  <span className="rounded-full border border-slate-800 px-3 py-1 text-slate-500">24h</span>
                </div>
              </div>
              <div className="mt-6">
                {latestNetworkTrail.length === 0 ? (
                  <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
                    Gathering network telemetry...
                  </div>
                ) : (
                  <svg viewBox="0 0 280 120" className="h-52 w-full" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="downloadGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="rgba(56,189,248,0.35)" />
                        <stop offset="100%" stopColor="rgba(15,23,42,0)" />
                      </linearGradient>
                      <linearGradient id="uploadGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="rgba(168,85,247,0.35)" />
                        <stop offset="100%" stopColor="rgba(15,23,42,0)" />
                      </linearGradient>
                    </defs>
                    <path d={downPaths.area} fill="url(#downloadGradient)" />
                    <path d={downPaths.line} stroke="rgba(56,189,248,0.75)" strokeWidth={3} fill="none" strokeLinecap="round" />
                    <path d={upPaths.area} fill="url(#uploadGradient)" />
                    <path d={upPaths.line} stroke="rgba(168,85,247,0.75)" strokeWidth={2} fill="none" strokeLinecap="round" />
                  </svg>
                )}
                <div className="mt-2 grid grid-cols-2 gap-4 text-sm text-slate-400">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-sky-400">Downlink</p>
                    <p className="mt-1 text-lg font-semibold text-white">{networkSnapshot.down.toFixed(1)} Mbps</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-violet-400">Uplink</p>
                    <p className="mt-1 text-lg font-semibold text-white">{networkSnapshot.up.toFixed(1)} Mbps</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="card border-slate-800/50 bg-slate-900/55">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-500">Storage Pools</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">Usage overview</h2>
                </div>
                <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">Optimal</span>
              </div>
              <div className="mt-6 flex flex-col items-center gap-6">
                <div className="relative flex h-40 w-40 items-center justify-center">
                  <div className="glow-ring h-36 w-36">
                    <div className="absolute inset-2 rounded-full border border-slate-900/80 bg-slate-950/80" />
                    <div className="glow-ring h-32 w-32 border-none" style={storageRingStyle}>
                      <div className="h-24 w-24 rounded-full bg-slate-950/90" />
                    </div>
                  </div>
                  <div className="absolute text-center">
                    <p className="text-3xl font-semibold text-white">{Math.round(storageStats.percent || 0)}%</p>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Used</p>
                  </div>
                </div>
                <div className="w-full space-y-4 text-sm">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300">
                      <span className="h-2 w-2 rounded-full bg-sky-400" />
                      Used capacity
                    </div>
                    <span className="text-slate-400">{formatBytes(storageStats.used)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300">
                      <span className="h-2 w-2 rounded-full bg-emerald-400" />
                      Available space
                    </div>
                    <span className="text-slate-400">{formatBytes(storageStats.available)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300">
                      <span className="h-2 w-2 rounded-full bg-slate-600" />
                      Total provisioned
                    </div>
                    <span className="text-slate-400">
                      {storageStats.total ? formatBytes(storageStats.total) : '—'}
                    </span>
                  </div>
                </div>
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
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">System Health</p>
                <h3 className="mt-2 text-lg font-semibold text-white">Telemetry summary</h3>
                <ul className="mt-5 space-y-3 text-sm text-slate-400">
                  <li className="flex items-center justify-between">
                    <span>Firmware</span>
                    <span className="rounded-full border border-slate-700/70 px-2 py-0.5 text-xs text-slate-200">v4.2.0</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Backup status</span>
                    <span className="text-emerald-300">Completed - 2m ago</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Active sessions</span>
                    <span className="text-slate-200">3 connected</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Alerts</span>
                    <span className="text-amber-300">0 pending</span>
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
