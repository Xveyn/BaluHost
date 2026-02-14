/**
 * Health Tab Component
 *
 * Displays system health information including:
 * - System stats (CPU, Memory, Disk, Uptime)
 * - SMART device information
 * - RAID status
 *
 * This is an embedded version of AdminHealth for use in SystemMonitor tabs.
 * Note: Backend services status is shown in the separate Services Tab.
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { buildApiUrl } from '../../lib/api';
import { formatBytes, formatUptime, formatNumber } from '../../lib/formatters';
import {
  RefreshCw,
  Cpu,
  HardDrive,
  MemoryStick,
  Thermometer,
  Activity,
} from 'lucide-react';

interface HealthData {
  status: string;
  system: {
    cpu: {
      usage: number;
      cores: number;
      frequency_mhz: number;
      temperature_celsius: number | null;
      model: string;
    };
    memory: {
      total: number;
      used: number;
      free: number;
      speed_mts?: number;
      type?: string;
    };
    disk: {
      total: number;
      used: number;
      free: number;
    };
    uptime: number;
    dev_mode: boolean;
  };
  smart?: {
    checked_at: string;
    devices: Array<{
      name: string;
      model: string;
      serial: string;
      temperature: number | null;
      status: string;
      capacity_bytes: number;
      used_bytes: number;
      used_percent: number;
      mount_point: string;
      attributes?: Array<{ id: number; name: string; raw: string }>;
    }>;
  };
  raid?: {
    arrays: Array<{
      name: string;
      level: number;
      status: string;
    }>;
  };
}


export function HealthTab() {
  const { t } = useTranslation('admin');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(buildApiUrl('/api/system/health'), {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setHealth(data);
    } catch (err: any) {
      setError(err?.message || t('health.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const refreshAll = () => {
    fetchHealth();
  };

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return (
    <div className="space-y-8 min-w-0">
      {/* Header with Refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t('health.title')}</h2>
          <p className="text-sm text-slate-400">{t('health.subtitle')}</p>
        </div>
        <button
          onClick={refreshAll}
          disabled={loading}
          className="flex items-center gap-2 min-h-[44px] rounded-xl border border-slate-700/70 bg-slate-800/50 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:border-sky-500/50 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? t('health.refreshing') : t('common:buttons.refresh')}
        </button>
      </div>

      {error && (
        <div className="card border-rose-500/30 bg-rose-500/10 text-sm text-rose-100">
          {error}
        </div>
      )}

      {/* System Stats */}
      {health && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-5">
          {/* CPU Card */}
          <div className="card border-slate-800/40 bg-slate-900/60">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/20">
                <Cpu className="h-5 w-5 text-violet-400" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">CPU</p>
                <p className="text-lg font-semibold text-white">{formatNumber(health.system.cpu.usage, 1)}%</p>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-400">
              <p className="truncate" title={health.system.cpu.model}>{health.system.cpu.model}</p>
              <p>{health.system.cpu.cores} cores @ {formatNumber(health.system.cpu.frequency_mhz / 1000, 2)} GHz</p>
              {health.system.cpu.temperature_celsius && (
                <p className="flex items-center gap-1">
                  <Thermometer className="h-3.5 w-3.5" />
                  {formatNumber(health.system.cpu.temperature_celsius, 1)}°C
                </p>
              )}
            </div>
          </div>

          {/* Memory Card */}
          <div className="card border-slate-800/40 bg-slate-900/60">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/20">
                <MemoryStick className="h-5 w-5 text-sky-400" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Memory</p>
                <p className="text-lg font-semibold text-white">{formatBytes(health.system.memory.used)}</p>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-400">
              <p>of {formatBytes(health.system.memory.total)} total</p>
              <p>{formatBytes(health.system.memory.free)} free</p>
              {health.system.memory.type && health.system.memory.speed_mts && (
                <p>{health.system.memory.type} @ {health.system.memory.speed_mts} MT/s</p>
              )}
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
                style={{ width: `${(health.system.memory.used / health.system.memory.total) * 100}%` }}
              />
            </div>
          </div>

          {/* Disk Card */}
          <div className="card border-slate-800/40 bg-slate-900/60">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/20">
                <HardDrive className="h-5 w-5 text-cyan-400" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Disk</p>
                <p className="text-lg font-semibold text-white">{formatBytes(health.system.disk.used)}</p>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-400">
              <p>of {formatBytes(health.system.disk.total)} total</p>
              <p>{formatBytes(health.system.disk.free)} free</p>
              {health.smart?.devices.length && (
                <p>{health.smart.devices.length} drive{health.smart.devices.length > 1 ? 's' : ''} detected</p>
              )}
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-sky-600"
                style={{ width: `${(health.system.disk.used / health.system.disk.total) * 100}%` }}
              />
            </div>
          </div>

          {/* Uptime Card */}
          <div className="card border-slate-800/40 bg-slate-900/60">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20">
                <Activity className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Uptime</p>
                <p className="text-lg font-semibold text-white">{formatUptime(health.system.uptime)}</p>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-400">
              <p>{t('health.systemStatus')}: <span className="text-emerald-400">{health.status}</span></p>
              <p>{t('health.mode')}: {health.system.dev_mode ? t('health.development') : t('health.production')}</p>
              {health.raid?.arrays.length ? (
                <p>{t('health.raidArrays', { count: health.raid.arrays.length })}</p>
              ) : (
                <p>{t('health.noRaidConfigured')}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* SMART Devices */}
      {health?.smart?.devices && health.smart.devices.length > 0 && (
        <div className="card border-slate-800/50 bg-slate-900/55">
          <div className="flex items-center gap-3 mb-6">
            <HardDrive className="h-5 w-5 text-sky-400" />
            <h2 className="text-lg font-semibold text-white">{t('health.storageDevices')}</h2>
          </div>
          <div className="space-y-3">
            {health.smart.devices.map((device) => (
              <div key={device.serial} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-slate-100">{device.model}</p>
                    <p className="text-xs text-slate-500">{device.name} • {device.serial}</p>
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${
                    device.status === 'PASSED'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : device.status === 'UNKNOWN'
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                      : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                  }`}>
                    {device.status}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.capacity')}</p>
                    <p className="text-slate-200">{formatBytes(device.capacity_bytes)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.used')}</p>
                    <p className="text-slate-200">{device.used_percent != null ? formatNumber(device.used_percent, 1) : '-'}%</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.mount')}</p>
                    <p className="text-slate-200">{device.mount_point}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.temperature')}</p>
                    <p className="text-slate-200">
                      {device.temperature !== null
                        ? `${device.temperature}°C`
                        : device.attributes?.find(a => a.id === 194)
                          ? `${device.attributes.find(a => a.id === 194)!.raw}°C`
                          : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
