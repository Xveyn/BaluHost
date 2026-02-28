import { useState, useEffect, useCallback } from 'react';
import {
  Power,
  Zap,
  Server,
  HardDrive,
  Cpu,
  Thermometer,
  Clock,
  Inbox,
  Activity,
  ShieldCheck,
  ShieldAlert,
  Wifi,
  WifiOff,
  RefreshCw,
} from 'lucide-react';
import { apiClient } from '../lib/api';
import { formatBytes, formatUptime } from '../lib/formatters';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HandshakeStatus {
  nas_state: string;
  since: string | null;
  last_snapshot: string | null;
  inbox_size_mb: number;
  inbox_files: number;
}

interface EnergyDevice {
  device_id: string;
  name: string;
  power_w: number;
  voltage_v: number;
  current_a: number;
}

interface EnergyCurrent {
  devices: EnergyDevice[];
  total_power_w: number;
}

interface PiSystem {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  temperature_c: number | null;
  uptime_seconds: number;
  hostname: string;
}

interface SnapshotData {
  version: number;
  generated_at: string;
  baluhost_version: string;
  system: {
    hostname: string;
    uptime_seconds: number;
    cpu_model: string;
    ram_total_gb: number;
  };
  storage: {
    arrays: Array<{
      name: string;
      level: string;
      state: string;
      size_bytes: number;
      devices: string[];
    }>;
    total_bytes: number;
    used_bytes: number;
  };
  smart_health: Record<string, {
    status: string;
    temperature_c: number | null;
    power_on_hours: number | null;
  }>;
  services: {
    vpn: { active_clients: number };
    shares: { active_shares: number };
    backups: { last_backup: string | null; status: string };
  };
  users: {
    total: number;
    list: Array<{ username: string; role: string }>;
  };
  files_summary: {
    total_files: number;
    total_size_bytes: number;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const NAS_STATES: Record<string, { label: string; color: string; bg: string; pulse: boolean }> = {
  online:        { label: 'Online',       color: 'text-emerald-400', bg: 'bg-emerald-500', pulse: false },
  booting:       { label: 'Booting',      color: 'text-amber-400',   bg: 'bg-amber-500',   pulse: true },
  shutting_down: { label: 'Shutting Down', color: 'text-amber-400',  bg: 'bg-amber-500',   pulse: true },
  offline:       { label: 'Offline',      color: 'text-slate-500',   bg: 'bg-slate-600',   pulse: false },
  unknown:       { label: 'Unknown',      color: 'text-slate-500',   bg: 'bg-slate-600',   pulse: false },
};

function timeAgo(iso: string | null): string {
  if (!iso) return '--';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PiDashboard() {
  const [handshake, setHandshake] = useState<HandshakeStatus | null>(null);
  const [energy, setEnergy] = useState<EnergyCurrent | null>(null);
  const [piSystem, setPiSystem] = useState<PiSystem | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotData | null>(null);
  const [wolLoading, setWolLoading] = useState(false);
  const [wolResult, setWolResult] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const [hs, en, sys, snap] = await Promise.allSettled([
        apiClient.get<HandshakeStatus>('/api/handshake/status'),
        apiClient.get<EnergyCurrent>('/api/energy/current'),
        apiClient.get<PiSystem>('/api/system/status'),
        apiClient.get<SnapshotData>('/api/snapshot'),
      ]);
      if (hs.status === 'fulfilled') setHandshake(hs.value.data);
      if (en.status === 'fulfilled') setEnergy(en.value.data);
      if (sys.status === 'fulfilled') setPiSystem(sys.value.data);
      if (snap.status === 'fulfilled') setSnapshot(snap.value.data);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleWol = async () => {
    setWolLoading(true);
    setWolResult(null);
    try {
      await apiClient.post('/api/nas/wol');
      setWolResult('WoL packet sent');
    } catch {
      setWolResult('Failed to send WoL');
    } finally {
      setWolLoading(false);
      setTimeout(() => setWolResult(null), 5000);
    }
  };

  const nasState = NAS_STATES[handshake?.nas_state ?? 'unknown'] ?? NAS_STATES.unknown;
  const storagePercent = snapshot?.storage.total_bytes
    ? Math.round((snapshot.storage.used_bytes / snapshot.storage.total_bytes) * 100)
    : 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 text-sm font-bold text-white">
            BP
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">BaluPi</h1>
            <p className="text-xs text-slate-500">{piSystem?.hostname ?? 'Pi'} Status Panel</p>
          </div>
        </div>
        <button
          onClick={fetchAll}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-400 transition hover:border-slate-600 hover:text-slate-300 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Top row: NAS Status + Energy */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* NAS Status Card */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-slate-400" />
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">NAS Status</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`h-2.5 w-2.5 rounded-full ${nasState.bg} ${nasState.pulse ? 'animate-pulse' : ''}`} />
              <span className={`text-sm font-semibold ${nasState.color}`}>{nasState.label}</span>
            </div>
          </div>

          <div className="space-y-2 text-xs text-slate-400">
            <div className="flex justify-between">
              <span>State since</span>
              <span className="text-slate-300">{timeAgo(handshake?.since ?? null)}</span>
            </div>
            <div className="flex justify-between">
              <span>Last snapshot</span>
              <span className="text-slate-300">{timeAgo(handshake?.last_snapshot ?? null)}</span>
            </div>
          </div>

          {/* WoL Button */}
          {handshake?.nas_state !== 'online' && handshake?.nas_state !== 'booting' && (
            <div className="mt-3 border-t border-slate-800 pt-3">
              <button
                onClick={handleWol}
                disabled={wolLoading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
              >
                <Power className="h-3.5 w-3.5" />
                {wolLoading ? 'Sending...' : 'Wake NAS'}
              </button>
              {wolResult && (
                <p className={`mt-1.5 text-center text-xs ${wolResult.includes('Failed') ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {wolResult}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Energy Card */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-400" />
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Energy</span>
          </div>

          {energy && energy.devices.length > 0 ? (
            <div className="space-y-3">
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold tabular-nums text-white">
                  {energy.total_power_w.toFixed(1)}
                </span>
                <span className="text-sm text-slate-400">W</span>
              </div>
              {energy.devices.map((dev) => (
                <div key={dev.device_id} className="flex items-center justify-between text-xs text-slate-400">
                  <span>{dev.name || dev.device_id}</span>
                  <div className="flex items-center gap-3">
                    <span className="tabular-nums text-slate-300">{dev.power_w.toFixed(1)} W</span>
                    <span className="tabular-nums">{dev.voltage_v.toFixed(0)} V</span>
                  </div>
                </div>
              ))}
              <div className="border-t border-slate-800 pt-2 text-xs text-slate-500">
                ~{((energy.total_power_w * 24) / 1000 * 0.30).toFixed(2)} EUR/day @0.30/kWh
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">No energy data available</p>
          )}
        </div>
      </div>

      {/* Middle row: Snapshot Data */}
      {snapshot && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-slate-400" />
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                NAS Snapshot
              </span>
            </div>
            <span className="text-xs text-slate-500">
              v{snapshot.baluhost_version} &middot; {timeAgo(snapshot.generated_at)}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Storage */}
            <div>
              <p className="mb-1 text-xs text-slate-500">Storage</p>
              <div className="mb-1.5 flex items-baseline gap-1">
                <span className="text-lg font-bold tabular-nums text-white">{storagePercent}%</span>
                <span className="text-xs text-slate-400">used</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className={`h-full rounded-full transition-all ${storagePercent > 90 ? 'bg-rose-500' : storagePercent > 70 ? 'bg-amber-500' : 'bg-sky-500'}`}
                  style={{ width: `${storagePercent}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatBytes(snapshot.storage.used_bytes)} / {formatBytes(snapshot.storage.total_bytes)}
              </p>
            </div>

            {/* RAID Arrays */}
            <div>
              <p className="mb-1 text-xs text-slate-500">RAID Arrays</p>
              {snapshot.storage.arrays.length > 0 ? (
                <div className="space-y-1.5">
                  {snapshot.storage.arrays.map((arr) => (
                    <div key={arr.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <div className={`h-1.5 w-1.5 rounded-full ${arr.state === 'active' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                        <span className="font-mono text-slate-300">{arr.name}</span>
                      </div>
                      <span className="text-slate-500">{arr.level.toUpperCase()} &middot; {arr.devices.length} disks</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">No arrays</p>
              )}
            </div>

            {/* Disk Health */}
            <div>
              <p className="mb-1 text-xs text-slate-500">Disk Health</p>
              {Object.keys(snapshot.smart_health).length > 0 ? (
                <div className="space-y-1.5">
                  {Object.entries(snapshot.smart_health).map(([name, health]) => (
                    <div key={name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        {health.status === 'PASSED' ? (
                          <ShieldCheck className="h-3 w-3 text-emerald-500" />
                        ) : (
                          <ShieldAlert className="h-3 w-3 text-rose-500" />
                        )}
                        <span className="font-mono text-slate-300">{name}</span>
                      </div>
                      {health.temperature_c != null && (
                        <span className="text-slate-500">{health.temperature_c}&deg;C</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">No SMART data</p>
              )}
            </div>
          </div>

          {/* Services summary row */}
          <div className="mt-3 flex flex-wrap gap-4 border-t border-slate-800 pt-3 text-xs text-slate-400">
            <div className="flex items-center gap-1.5">
              <Wifi className="h-3 w-3" />
              <span>{snapshot.services.vpn.active_clients} VPN clients</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Activity className="h-3 w-3" />
              <span>{snapshot.services.shares.active_shares} shares</span>
            </div>
            <div>
              {snapshot.users.total} users &middot; {snapshot.files_summary.total_files.toLocaleString()} files
            </div>
          </div>
        </div>
      )}

      {/* Bottom row: Pi Health + Inbox */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Pi System Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Cpu className="h-4 w-4 text-slate-400" />
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Pi Health</span>
          </div>

          {piSystem ? (
            <div className="grid grid-cols-2 gap-3">
              <Stat label="CPU" value={`${piSystem.cpu_percent.toFixed(0)}%`} warn={piSystem.cpu_percent > 80} />
              <Stat label="RAM" value={`${piSystem.memory_percent.toFixed(0)}%`} warn={piSystem.memory_percent > 85} />
              <Stat
                label="Temp"
                value={piSystem.temperature_c != null ? `${piSystem.temperature_c.toFixed(0)}\u00B0C` : '--'}
                warn={piSystem.temperature_c != null && piSystem.temperature_c > 70}
                icon={<Thermometer className="h-3 w-3" />}
              />
              <Stat
                label="Uptime"
                value={formatUptime(piSystem.uptime_seconds)}
                icon={<Clock className="h-3 w-3" />}
              />
            </div>
          ) : (
            <p className="text-xs text-slate-500">Loading...</p>
          )}
        </div>

        {/* Inbox Status */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Inbox className="h-4 w-4 text-slate-400" />
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">SMB Inbox</span>
          </div>

          {handshake ? (
            <div className="space-y-2">
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold tabular-nums text-white">
                  {handshake.inbox_files ?? 0}
                </span>
                <span className="text-sm text-slate-400">files</span>
              </div>
              <p className="text-xs text-slate-400">
                {(handshake.inbox_size_mb ?? 0).toFixed(1)} MB waiting
              </p>
              <p className="text-xs text-slate-500">
                {handshake.nas_state === 'online' ? (
                  <span className="flex items-center gap-1">
                    <Wifi className="h-3 w-3 text-emerald-500" />
                    Will flush on next sync
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <WifiOff className="h-3 w-3 text-slate-500" />
                    Queued until NAS comes online
                  </span>
                )}
              </p>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat sub-component
// ---------------------------------------------------------------------------

function Stat({ label, value, warn, icon }: { label: string; value: string; warn?: boolean; icon?: React.ReactNode }) {
  return (
    <div>
      <p className="mb-0.5 flex items-center gap-1 text-xs text-slate-500">
        {icon}
        {label}
      </p>
      <p className={`text-sm font-semibold tabular-nums ${warn ? 'text-amber-400' : 'text-slate-200'}`}>
        {value}
      </p>
    </div>
  );
}
