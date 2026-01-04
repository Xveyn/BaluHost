import { useEffect, useState } from 'react';
import { Activity, FolderSync, TrendingUp, TrendingDown, Cpu, HardDrive, Clock, Zap } from 'lucide-react';
import toast from 'react-hot-toast';
import { formatBytes, formatUptime } from '../../lib/formatters';
import { getMemoryPercent, getDiskPercent } from '../../lib/calculations';
import { BackendMessage } from '../../lib/types';

interface DashboardProps {
  user: { username: string; serverUrl?: string };
  onLogout: () => void;
}

interface SyncStats {
  status: string;
  uploadSpeed: number;
  downloadSpeed: number;
  pendingUploads: number;
  pendingDownloads: number;
  lastSync: string;
  syncFolderCount?: number;
}

interface RaidDevice {
  name: string;
  state: string;
}

interface RaidArray {
  name: string;
  level: string;
  status: string;
  size_bytes: number;
  resync_progress?: number;
  devices: RaidDevice[];
}

interface RaidStatus {
  arrays: RaidArray[];
  dev_mode?: boolean;
}

interface SystemInfo {
  cpu: {
    usage: number;
    cores: number;
    frequency_mhz?: number | null;
    model?: string | null;
  };
  memory: {
    total: number;
    used: number;
    free: number;
    speed_mts?: number | null;
    type?: string | null;
  };
  disk: {
    total: number;
    used: number;
    free: number;
  };
  uptime: number;
  dev_mode?: boolean;
}

export default function Dashboard({ user, onLogout }: DashboardProps) {
  const [syncStats, setSyncStats] = useState<SyncStats | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [raidStatus, setRaidStatus] = useState<RaidStatus | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Listen to backend messages
    window.electronAPI.onBackendMessage((message: BackendMessage) => {
      console.log('Backend message:', message);
      
      if (message.type === 'sync_stats') {
        setSyncStats(message.data);
      }
    });

    // Request initial data
    fetchData();

    return () => {
      window.electronAPI.removeBackendListener();
    };
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch sync state
      try {
        const syncResponse = await window.electronAPI.sendBackendCommand({
          type: 'get_sync_state',
        });
        if (syncResponse?.success) {
          setSyncStats(syncResponse.data);
        }
      } catch (err) {
        console.error('Failed to fetch sync state:', err);
      }

      // Fetch system info
      try {
        const sysResponse = await window.electronAPI.sendBackendCommand({
          type: 'get_system_info',
        });
        if (sysResponse?.success) {
          setSystemInfo(sysResponse.data);
        } else {
          console.warn('System info response not successful:', sysResponse);
        }
      } catch (err) {
        console.error('Failed to fetch system info:', err);
      }

      // Fetch RAID status
      try {
        const raidResponse = await window.electronAPI.sendBackendCommand({
          type: 'get_raid_status',
        });
        if (raidResponse?.success) {
          setRaidStatus(raidResponse.data);
        }
      } catch (err) {
        console.error('Failed to fetch RAID status:', err);
      }
    } finally {
      setLoading(false);
    }
  };

  const getMemoryPercentage = (): number => {
    if (!systemInfo) return 0;
    return getMemoryPercent(systemInfo.memory);
  };

  const getDiskPercentage = (): number => {
    if (!systemInfo) return 0;
    return getDiskPercent(systemInfo.disk);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center space-x-3">
          <div className="rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 p-3">
            <Activity className="h-6 w-6 text-white" />
          </div>
          <span>Dashboard</span>
        </h1>
        <p className="mt-2 text-slate-400">Monitor your sync status and activity</p>
      </div>

      {/* Sync Status Cards */}
      <div className="grid gap-6 md:grid-cols-4">
        {/* Status Card */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-blue-500/10 to-blue-600/10 p-6 backdrop-blur-sm transition-all hover:border-blue-500/30 hover:shadow-lg hover:shadow-blue-500/20">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-400">Sync Status</p>
              <div className="rounded-lg bg-blue-500/20 p-2">
                <Activity className="h-4 w-4 text-blue-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {syncStats?.status || 'Idle'}
            </p>
          </div>
        </div>

        {/* Upload Queue Card */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-emerald-500/10 to-emerald-600/10 p-6 backdrop-blur-sm transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/20">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-400">Upload Queue</p>
              <div className="rounded-lg bg-emerald-500/20 p-2">
                <TrendingUp className="h-4 w-4 text-emerald-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {syncStats?.pendingUploads || 0}
            </p>
            {syncStats?.uploadSpeed && (
              <p className="text-xs text-slate-400">
                {(syncStats.uploadSpeed / 1024 / 1024).toFixed(2)} MB/s
              </p>
            )}
          </div>
        </div>

        {/* Download Queue Card */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-purple-500/10 to-purple-600/10 p-6 backdrop-blur-sm transition-all hover:border-purple-500/30 hover:shadow-lg hover:shadow-purple-500/20">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-400">Download Queue</p>
              <div className="rounded-lg bg-purple-500/20 p-2">
                <TrendingDown className="h-4 w-4 text-purple-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {syncStats?.pendingDownloads || 0}
            </p>
            {syncStats?.downloadSpeed && (
              <p className="text-xs text-slate-400">
                {(syncStats.downloadSpeed / 1024 / 1024).toFixed(2)} MB/s
              </p>
            )}
          </div>
        </div>

        {/* Sync Folders Card */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-orange-500/10 to-orange-600/10 p-6 backdrop-blur-sm transition-all hover:border-orange-500/30 hover:shadow-lg hover:shadow-orange-500/20">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-400">Sync Folders</p>
              <div className="rounded-lg bg-orange-500/20 p-2">
                <FolderSync className="h-4 w-4 text-orange-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {syncStats?.syncFolderCount || 0}
            </p>
          </div>
        </div>
      </div>

      {/* System Metrics Cards */}
      <div className="grid gap-6 md:grid-cols-4">
        {loading ? (
          // Skeleton loading state
          <>
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-white/10 bg-white/5 p-6 backdrop-blur-sm"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="h-4 w-20 bg-slate-700 rounded animate-pulse" />
                    <div className="h-8 w-8 bg-slate-700 rounded animate-pulse" />
                  </div>
                  <div className="h-8 w-16 bg-slate-700 rounded animate-pulse" />
                </div>
              </div>
            ))}
          </>
        ) : systemInfo ? (
          // Data loaded successfully
          <>
            {/* CPU Card */}
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-cyan-500/10 to-cyan-600/10 p-6 backdrop-blur-sm transition-all hover:border-cyan-500/30 hover:shadow-lg hover:shadow-cyan-500/20">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">CPU</p>
                  <div className="rounded-lg bg-cyan-500/20 p-2">
                    <Cpu className="h-4 w-4 text-cyan-400" />
                  </div>
                </div>
                <p className="text-3xl font-bold text-white">
                  {systemInfo.cpu.usage.toFixed(1)}%
                </p>
                <div className="space-y-1">
                  <p className="text-xs text-slate-400">
                    {systemInfo.cpu.cores} cores
                  </p>
                  {systemInfo.cpu.frequency_mhz && (
                    <p className="text-xs text-slate-400">
                      {systemInfo.cpu.frequency_mhz.toFixed(0)} MHz
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Memory Card */}
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-pink-500/10 to-pink-600/10 p-6 backdrop-blur-sm transition-all hover:border-pink-500/30 hover:shadow-lg hover:shadow-pink-500/20">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">RAM</p>
                  <div className="rounded-lg bg-pink-500/20 p-2">
                    <div className="h-4 w-4 bg-pink-400 rounded" />
                  </div>
                </div>
                <p className="text-3xl font-bold text-white">
                  {getMemoryPercentage().toFixed(1)}%
                </p>
                <div className="space-y-1">
                  <div className="h-1.5 w-full bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-pink-500 to-pink-600 transition-all"
                      style={{ width: `${Math.min(getMemoryPercentage(), 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-400">
                    {formatBytes(systemInfo.memory.used)} / {formatBytes(systemInfo.memory.total)}
                  </p>
                </div>
              </div>
            </div>

            {/* Disk Card */}
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-amber-500/10 to-amber-600/10 p-6 backdrop-blur-sm transition-all hover:border-amber-500/30 hover:shadow-lg hover:shadow-amber-500/20">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">Disk</p>
                  <div className="rounded-lg bg-amber-500/20 p-2">
                    <HardDrive className="h-4 w-4 text-amber-400" />
                  </div>
                </div>
                <p className="text-3xl font-bold text-white">
                  {getDiskPercentage().toFixed(1)}%
                </p>
                <div className="space-y-1">
                  <div className="h-1.5 w-full bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all"
                      style={{ width: `${Math.min(getDiskPercentage(), 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-400">
                    {formatBytes(systemInfo.disk.used)} / {formatBytes(systemInfo.disk.total)}
                  </p>
                </div>
              </div>
            </div>

            {/* Uptime Card */}
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-lime-500/10 to-lime-600/10 p-6 backdrop-blur-sm transition-all hover:border-lime-500/30 hover:shadow-lg hover:shadow-lime-500/20">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">Uptime</p>
                  <div className="rounded-lg bg-lime-500/20 p-2">
                    <Clock className="h-4 w-4 text-lime-400" />
                  </div>
                </div>
                <p className="text-3xl font-bold text-white">
                  {formatUptime(systemInfo.uptime)}
                </p>
                <p className="text-xs text-slate-400">
                  {(systemInfo.uptime / 86400).toFixed(1)} days
                </p>
              </div>
            </div>
          </>
        ) : (
          // Error state
          <div className="col-span-4 rounded-xl border border-red-500/30 bg-red-500/10 p-6">
            <p className="text-sm text-red-400">
              Unable to load system information. Please try refreshing.
            </p>
          </div>
        )}
      </div>

      {/* RAID Status Section */}
      {raidStatus && raidStatus.arrays && raidStatus.arrays.length > 0 && (
        <div className="space-y-4">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center space-x-3">
              <div className="rounded-lg bg-gradient-to-br from-red-500 to-red-600 p-2">
                <Zap className="h-5 w-5 text-white" />
              </div>
              <span>RAID Status</span>
            </h2>
          </div>

          <div className="grid gap-4">
            {raidStatus.arrays.map((array) => (
              <div
                key={array.name}
                className={`rounded-xl border p-4 transition-all ${
                  array.status === 'optimal'
                    ? 'border-emerald-500/30 bg-emerald-500/10'
                    : array.status === 'degraded'
                      ? 'border-amber-500/30 bg-amber-500/10'
                      : array.status === 'rebuilding'
                        ? 'border-blue-500/30 bg-blue-500/10'
                        : 'border-slate-700/50 bg-slate-900/30'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-semibold text-white">
                      {array.name} - RAID{array.level.replace('RAID', '')}
                    </p>
                    <p className="text-sm text-slate-400">
                      {formatBytes(array.size_bytes)} 
                      {array.status === 'rebuilding' &&
                        ` (${array.resync_progress?.toFixed(1) || 0}% synced)`}
                    </p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      array.status === 'optimal'
                        ? 'bg-emerald-500/30 text-emerald-200'
                        : array.status === 'degraded'
                          ? 'bg-amber-500/30 text-amber-200'
                          : array.status === 'rebuilding'
                            ? 'bg-blue-500/30 text-blue-200'
                            : 'bg-slate-700/30 text-slate-300'
                    }`}
                  >
                    {array.status.charAt(0).toUpperCase() + array.status.slice(1)}
                  </span>
                </div>

                {/* Devices */}
                <div className="space-y-2">
                  {array.devices.map((device) => (
                    <div
                      key={device.name}
                      className={`text-xs rounded px-2 py-1 ${
                        device.state === 'active'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : device.state === 'failed'
                            ? 'bg-red-500/20 text-red-300'
                            : device.state === 'spare'
                              ? 'bg-blue-500/20 text-blue-300'
                              : 'bg-slate-700/20 text-slate-300'
                      }`}
                    >
                      {device.name} ({device.state})
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last Sync Info */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
        <p className="text-sm text-slate-400">
          <span className="font-medium text-slate-300">Last sync:</span>{' '}
          {syncStats?.lastSync || 'Never'}
        </p>
      </div>
    </div>
  );
}
