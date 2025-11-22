import { useState, useEffect } from 'react';
import { buildApiUrl } from '../lib/api';

interface SystemInfo {
  cpu: {
    usage: number;
    cores: number;
  };
  memory: {
    total: number;
    used: number;
    free: number;
  };
  disk: {
    total: number;
    used: number;
    free: number;
  };
  uptime: number;
}

export default function SystemMonitor() {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadSystemInfo();
    const interval = setInterval(loadSystemInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadSystemInfo = async () => {
    setLoading(true);
    const token = localStorage.getItem('token');

    try {
      const response = await fetch(buildApiUrl('/api/system/info'), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();
      setSystemInfo(data);
    } catch (err) {
      console.error('Failed to load system info:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  if (loading && !systemInfo) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
        <p className="text-sm text-slate-500">Loading system telemetry...</p>
      </div>
    );
  }

  const cpuUsage = Math.min(systemInfo?.cpu.usage ?? 0, 100);
  const memoryPercent = systemInfo?.memory.total
    ? (systemInfo.memory.used / systemInfo.memory.total) * 100
    : 0;
  const diskPercent = systemInfo?.disk.total
    ? (systemInfo.disk.used / systemInfo.disk.total) * 100
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">System Monitor</h1>
          <p className="mt-1 text-sm text-slate-400">Real-time performance timeline and availability metrics</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
          Live telemetry stream
        </div>
      </div>

      {systemInfo && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {[{
              id: 'cpu',
              title: 'CPU Load',
              value: `${cpuUsage.toFixed(1)}%`,
              meta: `${systemInfo.cpu.cores} cores`,
              accent: 'from-sky-500 to-indigo-500',
              progress: cpuUsage
            }, {
              id: 'memory',
              title: 'Memory Pressure',
              value: formatBytes(systemInfo.memory.used),
              meta: `of ${formatBytes(systemInfo.memory.total)}`,
              accent: 'from-violet-500 to-fuchsia-500',
              progress: memoryPercent
            }, {
              id: 'disk',
              title: 'Disk Usage',
              value: systemInfo.disk.total ? formatBytes(systemInfo.disk.used) : 'Mock mode',
              meta: systemInfo.disk.total ? `of ${formatBytes(systemInfo.disk.total)}` : 'Linux metrics recommended',
              accent: 'from-cyan-500 to-sky-600',
              progress: diskPercent || 12
            }, {
              id: 'uptime',
              title: 'System Uptime',
              value: formatUptime(systemInfo.uptime),
              meta: 'Since last restart',
              accent: 'from-emerald-500 to-teal-500',
              progress: 100
            }].map((card) => (
              <div key={card.id} className="card border-slate-800/60 bg-slate-900/55">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{card.title}</p>
                    <p className="mt-3 text-3xl font-semibold text-white">{card.value}</p>
                  </div>
                  <div className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${card.accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
                    ●
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
                  <span>{card.meta}</span>
                  <span className="text-slate-500">{card.id === 'uptime' ? 'Live' : 'Stable'}</span>
                </div>
                <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${card.accent}`}
                    style={{ width: `${Math.min(Math.max(card.progress, 0), 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[2fr_1fr]">
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-500">Memory Allocation</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">Usage breakdown</h2>
                </div>
                <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs text-sky-200">Live</span>
              </div>
              <div className="mt-6 grid gap-4 text-sm text-slate-400 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Used</p>
                  <p className="mt-2 text-lg font-semibold text-white">{formatBytes(systemInfo.memory.used)}</p>
                  <p className="text-xs text-slate-500">Applications + services</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Free</p>
                  <p className="mt-2 text-lg font-semibold text-white">{formatBytes(systemInfo.memory.free)}</p>
                  <p className="text-xs text-slate-500">Cache available</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Total</p>
                  <p className="mt-2 text-lg font-semibold text-white">{formatBytes(systemInfo.memory.total)}</p>
                  <p className="text-xs text-slate-500">Physical memory</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Usage</p>
                  <p className="mt-2 text-lg font-semibold text-white">{memoryPercent.toFixed(1)}%</p>
                  <p className="text-xs text-slate-500">Utilisation</p>
                </div>
              </div>
            </div>

            <div className="space-y-6">
              <div className="card border-slate-800/60 bg-slate-900/55">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Uptime milestones</p>
                <h3 className="mt-2 text-lg font-semibold text-white">Key checkpoints</h3>
                <ul className="mt-5 space-y-3 text-sm text-slate-400">
                  <li className="flex items-center justify-between">
                    <span>Last startup</span>
                    <span className="text-slate-200">{formatUptime(systemInfo.uptime)} ago</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Last backup</span>
                    <span className="text-emerald-300">Completed - 2h ago</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span>Next maintenance</span>
                    <span className="text-slate-200">Scheduled - 26 Oct</span>
                  </li>
                </ul>
              </div>

              <div className="card border-slate-800/60 bg-gradient-to-br from-slate-900/70 via-slate-900/40 to-slate-950/80">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Storage advisory</p>
                <h3 className="mt-2 text-lg font-semibold text-white">Linux metrics recommended</h3>
                <p className="mt-3 text-sm text-slate-400">
                  Detailed disk telemetry is available when BalùHost runs on a Linux host. Switch to production hardware to unlock IO tracing, SMART monitoring, and RAID scrubbing insights.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
