import { useEffect, useState } from 'react';
import { Activity, FolderSync, TrendingUp, TrendingDown, Cpu, HardDrive, Clock, Zap, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { formatBytes, formatUptime, formatTimestamp } from '../../lib/formatters';
import { getMemoryPercent, getDiskPercent } from '../../lib/calculations';
import { BackendMessage } from '../../lib/types';
import { PowerCard } from '../components/PowerCard';

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
  serverUptime?: number;
  dev_mode?: boolean;
}

export default function Dashboard({ user: _user, onLogout: _onLogout }: DashboardProps) {
  const [syncStats, setSyncStats] = useState<SyncStats | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [raidStatus, setRaidStatus] = useState<RaidStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [devMode, setDevMode] = useState<'prod' | 'mock'>('prod');

  // Helper: Format transfer speed
  const formatSpeed = (bytesPerSecond: number): string => {
    if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} B/s`;
    if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`;
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
  };

  useEffect(() => {
    // Listen to backend messages
    window.electronAPI.onBackendMessage((message: BackendMessage) => {
      console.log('Backend message:', message);
      
      // Handle different sync event shapes coming from the backend
      if (message.type === 'sync_stats') {
        setSyncStats(message.data);
      } else if (message.type === 'sync_state_update') {
        // Live broadcast from SyncEngine
        setSyncStats(message.data);
      } else if (message.type === 'sync_state') {
        // Could be a direct event or legacy response forwarded
        if ((message as any).success && (message as any).data) {
          setSyncStats((message as any).data);
        } else if ((message as any).status) {
          // Legacy shape
          const legacy = message as any;
          const mapped: SyncStats = {
            status: legacy.status || 'idle',
            uploadSpeed: legacy.upload_speed ?? legacy.uploadSpeed ?? 0,
            downloadSpeed: legacy.download_speed ?? legacy.downloadSpeed ?? 0,
            pendingUploads: legacy.pendingUploads ?? legacy.pending_uploads ?? 0,
            pendingDownloads: legacy.pendingDownloads ?? legacy.pending_downloads ?? 0,
            lastSync: legacy.last_sync ?? legacy.lastSync ?? ''
          };
          if ((legacy.syncFolderCount ?? legacy.sync_folder_count) !== undefined) {
            (mapped as any).syncFolderCount = legacy.syncFolderCount ?? legacy.sync_folder_count;
          }
          setSyncStats(mapped);
        }
      }
    });

    // Request initial data
    fetchData();

    return () => {
      window.electronAPI.removeBackendListener();
    };
  }, []);

  // Fetch dev mode setting on mount
  useEffect(() => {
    const fetchDevMode = async () => {
      try {
        const response = await window.electronAPI.sendBackendCommand({
          type: 'get_dev_mode'
        });
        if (response?.success && response.data?.devMode) {
          setDevMode(response.data.devMode);
        }
      } catch (err) {
        console.error('Failed to fetch dev mode:', err);
      }
    };
    fetchDevMode();
  }, []);

  // Toggle dev mode and refresh data
  const handleDevModeToggle = async (newMode: 'prod' | 'mock') => {
    try {
      const response = await window.electronAPI.sendBackendCommand({
        type: 'set_dev_mode',
        data: { devMode: newMode }
      });

      if (response?.success) {
        setDevMode(newMode);
        // Refresh data immediately after mode switch
        fetchData();
      }
    } catch (err) {
      console.error('Failed to toggle dev mode:', err);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch sync state
      try {
        const syncResponse = await window.electronAPI.sendBackendCommand({ type: 'get_sync_state' });

        // New format: { success: true, data: { ... } }
        if (syncResponse?.success && syncResponse.data) {
          setSyncStats(syncResponse.data);
        } else if (syncResponse) {
          // Backwards-compatible handling for legacy response shape
          // Legacy example: { type: 'sync_state', status: 'idle', upload_speed: 0, download_speed: 0, last_sync: '' }
          const legacy = syncResponse as any;
          if (legacy.type === 'sync_state') {
            const mapped: SyncStats = {
              status: legacy.status || 'idle',
              uploadSpeed: legacy.upload_speed ?? legacy.uploadSpeed ?? 0,
              downloadSpeed: legacy.download_speed ?? legacy.downloadSpeed ?? 0,
              pendingUploads: legacy.pendingUploads ?? legacy.pending_uploads ?? 0,
              pendingDownloads: legacy.pendingDownloads ?? legacy.pending_downloads ?? 0,
              lastSync: legacy.last_sync ?? legacy.lastSync ?? ''
            };
            // Optionally include syncFolderCount if present
            if ((legacy.syncFolderCount ?? legacy.sync_folder_count) !== undefined) {
              (mapped as any).syncFolderCount = legacy.syncFolderCount ?? legacy.sync_folder_count;
            }
            setSyncStats(mapped);
          }
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
          // Normalize system info fields for frontend expectations
          const raw = sysResponse.data as any;
          const normalized: any = { ...raw };

          // CPU frequency mapping: backend may use `frequency` or `frequency_mhz`
          if (raw?.cpu) {
            normalized.cpu = {
              usage: raw.cpu.usage ?? 0,
              cores: raw.cpu.cores ?? raw.cpu.coreCount ?? 0,
              frequency_mhz: raw.cpu.frequency_mhz ?? raw.cpu.frequency ?? null,
              model: raw.cpu.model ?? null,
            };
          }

          // Disk mapping: backend may provide `available` or `free`
          if (raw?.disk) {
            normalized.disk = {
              total: raw.disk.total ?? raw.disk.total_bytes ?? 0,
              used: raw.disk.used ?? (raw.disk.total - (raw.disk.available ?? raw.disk.free ?? 0)),
              available: raw.disk.available ?? raw.disk.free ?? null,
            };
          }

          // Uptime: backend sends seconds; but if it's unexpectedly large assume milliseconds
          if (typeof raw?.uptime === 'number') {
            let uptimeSeconds = raw.uptime;
            if (uptimeSeconds > 1e12) {
              // milliseconds -> seconds
              uptimeSeconds = Math.floor(uptimeSeconds / 1000);
            }
            normalized.uptime = uptimeSeconds;
          }

          // serverUptime: if provided, normalize same as uptime (guard against ms values)
          if (typeof raw?.serverUptime === 'number') {
            let sUptime = raw.serverUptime;
            if (sUptime > 1e12) {
              sUptime = Math.floor(sUptime / 1000);
            }
            normalized.serverUptime = sUptime;
          }

          setSystemInfo(normalized as any);
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center space-x-3">
            <div className="rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 p-3">
              <Activity className="h-6 w-6 text-white" />
            </div>
            <span>Dashboard</span>
          </h1>
          <p className="mt-2 text-slate-400">
            Monitor your sync status and activity • Last sync: {syncStats?.lastSync ? formatTimestamp(syncStats.lastSync) : 'Never'}
          </p>
        </div>

        {/* Dev-Mode Toggle */}
        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400">Data Source:</span>
          <button
            onClick={() => handleDevModeToggle('prod')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              devMode === 'prod'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            Server
          </button>
          <button
            onClick={() => handleDevModeToggle('mock')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              devMode === 'mock'
                ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/30'
                : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            Mock
          </button>
        </div>
      </div>

      {/* Dev-Mode Indikator */}
      {devMode === 'mock' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="flex items-center space-x-2">
            <span className="text-amber-400">⚠️</span>
            <p className="text-sm text-amber-200">
              Mock data mode active. Dashboard shows test data (8 cores, 45% CPU, 16GB RAM, 1TB disk).
            </p>
          </div>
        </div>
      )}

      {/* Sync Overview */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Sync Activity Card (Combined Upload + Download) */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-emerald-500/10 via-purple-500/10 to-purple-600/10 p-4 backdrop-blur-sm transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/20">
          <div className="flex items-center space-x-2 mb-3">
            <div className="rounded-lg bg-gradient-to-br from-emerald-500/20 to-purple-500/20 p-1.5">
              <ArrowUpDown className="h-4 w-4 text-emerald-400" />
            </div>
            <h3 className="text-sm font-medium text-slate-300">Sync Activity</h3>
          </div>

          <div className="space-y-2">
            {/* Upload Section */}
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <ArrowUp className="h-4 w-4 text-emerald-400" />
                <span className="text-xs text-slate-400">Uploads</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-sm font-semibold text-white">
                  {syncStats?.pendingUploads || 0}
                </span>
                {syncStats?.uploadSpeed && syncStats.uploadSpeed > 0 && (
                  <span className="text-xs text-emerald-400">
                    {formatSpeed(syncStats.uploadSpeed)}
                  </span>
                )}
              </div>
            </div>

            {/* Download Section */}
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <ArrowDown className="h-4 w-4 text-purple-400" />
                <span className="text-xs text-slate-400">Downloads</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-sm font-semibold text-white">
                  {syncStats?.pendingDownloads || 0}
                </span>
                {syncStats?.downloadSpeed && syncStats.downloadSpeed > 0 && (
                  <span className="text-xs text-purple-400">
                    {formatSpeed(syncStats.downloadSpeed)}
                  </span>
                )}
              </div>
            </div>

            {/* Total Pending */}
            <div className="mt-2 pt-2 border-t border-white/10">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">Total Pending</span>
                <span className="text-lg font-bold text-white">
                  {(syncStats?.pendingUploads || 0) + (syncStats?.pendingDownloads || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Sync Folders Card */}
        <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-orange-500/10 to-orange-600/10 p-4 backdrop-blur-sm transition-all hover:border-orange-500/30 hover:shadow-lg hover:shadow-orange-500/20">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-400">Sync Folders</p>
              <div className="rounded-lg bg-orange-500/20 p-1.5">
                <FolderSync className="h-4 w-4 text-orange-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {syncStats?.syncFolderCount || 0}
            </p>
          </div>
        </div>
      </div>

      {/* System Metrics */}
      <div className="space-y-6">
        {/* Row 1: CPU, RAM, Disk */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {loading ? (
            // Skeleton loading state
            <>
              {[...Array(3)].map((_, i) => (
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
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-cyan-500/10 to-cyan-600/10 p-4 backdrop-blur-sm transition-all hover:border-cyan-500/30 hover:shadow-lg hover:shadow-cyan-500/20">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">CPU</p>
                  <div className="rounded-lg bg-cyan-500/20 p-1.5">
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
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-pink-500/10 to-pink-600/10 p-4 backdrop-blur-sm transition-all hover:border-pink-500/30 hover:shadow-lg hover:shadow-pink-500/20">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">RAM</p>
                  <div className="rounded-lg bg-pink-500/20 p-1.5">
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
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-amber-500/10 to-amber-600/10 p-4 backdrop-blur-sm transition-all hover:border-amber-500/30 hover:shadow-lg hover:shadow-amber-500/20">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">Disk</p>
                  <div className="rounded-lg bg-amber-500/20 p-1.5">
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
          </>
        ) : (
          // Error state
          <div className="col-span-full rounded-xl border border-red-500/30 bg-red-500/10 p-6">
            <p className="text-sm text-red-400">
              Unable to load system information. Please try refreshing.
            </p>
          </div>
        )}
        </div>

        {/* Row 2: Uptime, Power */}
        <div className="grid gap-6 md:grid-cols-2">
          {loading ? (
            <>
              {[...Array(2)].map((_, i) => (
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
            <>
              {/* Uptime Card */}
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-lime-500/10 to-lime-600/10 p-4 backdrop-blur-sm transition-all hover:border-lime-500/30 hover:shadow-lg hover:shadow-lime-500/20">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-400">Uptime</p>
                  <div className="rounded-lg bg-lime-500/20 p-1.5">
                    <Clock className="h-4 w-4 text-lime-400" />
                  </div>
                </div>
                {(() => {
                  const serverU = (systemInfo as any).serverUptime;
                  const uptimeToShow = (typeof serverU === 'number' && serverU > 0) ? serverU : systemInfo.uptime;
                  return (
                    <>
                      <p className="text-3xl font-bold text-white">{formatUptime(uptimeToShow)}</p>
                      <p className="text-xs text-slate-400">{(uptimeToShow / 86400).toFixed(1)} days</p>
                    </>
                  );
                })()}
              </div>
            </div>

              {/* Power Card */}
              <PowerCard />
            </>
          ) : (
            // Error state
            <div className="col-span-full rounded-xl border border-red-500/30 bg-red-500/10 p-6">
              <p className="text-sm text-red-400">
                Unable to load system information. Please try refreshing.
              </p>
            </div>
          )}
        </div>
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

    </div>
  );
}
