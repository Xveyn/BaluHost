import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { buildApiUrl } from '../lib/api';
import { getAllServices, type ServiceStatus, ServiceState } from '../api/service-status';
import {
  Server,
  CheckCircle2,
  XCircle,
  MinusCircle,
  AlertCircle,
  RefreshCw,
  Cpu,
  HardDrive,
  MemoryStick,
  Thermometer,
  Clock,
  Activity,
  ArrowLeft,
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

const formatBytes = (bytes: number): string => {
  if (!bytes || Number.isNaN(bytes)) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(1)} ${units[i]}`;
};

const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
};

const getStateIcon = (state: string) => {
  switch (state) {
    case ServiceState.RUNNING:
      return <CheckCircle2 className="h-5 w-5 text-emerald-400" />;
    case ServiceState.STOPPED:
      return <MinusCircle className="h-5 w-5 text-slate-400" />;
    case ServiceState.ERROR:
      return <XCircle className="h-5 w-5 text-rose-400" />;
    case ServiceState.DISABLED:
      return <AlertCircle className="h-5 w-5 text-amber-400" />;
    default:
      return <MinusCircle className="h-5 w-5 text-slate-400" />;
  }
};

const getStateBadgeClass = (state: string) => {
  switch (state) {
    case ServiceState.RUNNING:
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
    case ServiceState.STOPPED:
      return 'border-slate-500/30 bg-slate-500/10 text-slate-300';
    case ServiceState.ERROR:
      return 'border-rose-500/30 bg-rose-500/10 text-rose-300';
    case ServiceState.DISABLED:
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
    default:
      return 'border-slate-500/30 bg-slate-500/10 text-slate-300';
  }
};

export default function AdminHealth() {
  const navigate = useNavigate();
  const { t } = useTranslation('admin');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [servicesLoading, setServicesLoading] = useState(true);
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
  }, []);

  const fetchServices = useCallback(async () => {
    setServicesLoading(true);
    try {
      const data = await getAllServices();
      setServices(data);
    } catch (err: any) {
      console.error('Failed to load services:', err);
    } finally {
      setServicesLoading(false);
    }
  }, []);

  const refreshAll = () => {
    fetchHealth();
    fetchServices();
  };

  useEffect(() => {
    fetchHealth();
    fetchServices();
  }, [fetchHealth, fetchServices]);

  const serviceSummary = {
    running: services.filter(s => s.state === ServiceState.RUNNING).length,
    stopped: services.filter(s => s.state === ServiceState.STOPPED).length,
    error: services.filter(s => s.state === ServiceState.ERROR).length,
    disabled: services.filter(s => s.state === ServiceState.DISABLED).length,
    total: services.length,
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700/70 bg-slate-800/50 text-slate-400 transition hover:border-sky-500/50 hover:text-white"
            title={t('health.backToDashboard')}
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('health.title')}</h1>
            <p className="mt-1 text-sm text-slate-400">{t('health.subtitle')}</p>
          </div>
        </div>
        <button
          onClick={refreshAll}
          disabled={loading || servicesLoading}
          className="flex items-center gap-2 min-h-[44px] rounded-xl border border-slate-700/70 bg-slate-800/50 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:border-sky-500/50 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading || servicesLoading ? 'animate-spin' : ''}`} />
          {loading || servicesLoading ? t('health.refreshing') : t('common:buttons.refresh')}
        </button>
      </div>

      {error && (
        <div className="card border-rose-500/30 bg-rose-500/10 text-sm text-rose-100">
          {error}
        </div>
      )}

      {/* Services Section */}
      <div className="card border-slate-800/50 bg-slate-900/55">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Server className="h-5 w-5 text-sky-400" />
            <h2 className="text-lg font-semibold text-white">{t('health.backendServices')}</h2>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-emerald-300">{t('health.serviceLabels.running', { count: serviceSummary.running })}</span>
            </span>
            {serviceSummary.stopped > 0 && (
              <span className="flex items-center gap-1.5">
                <MinusCircle className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-slate-400">{t('health.serviceLabels.stopped', { count: serviceSummary.stopped })}</span>
              </span>
            )}
            {serviceSummary.error > 0 && (
              <span className="flex items-center gap-1.5">
                <XCircle className="h-3.5 w-3.5 text-rose-400" />
                <span className="text-rose-300">{t('health.serviceLabels.error', { count: serviceSummary.error })}</span>
              </span>
            )}
          </div>
        </div>

        {servicesLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="h-5 w-32 rounded bg-slate-800 animate-pulse mb-2" />
                <div className="h-4 w-20 rounded bg-slate-800/50 animate-pulse" />
              </div>
            ))}
          </div>
        ) : services.length === 0 ? (
          <div className="text-center py-8 text-slate-500">
            {t('health.noServicesRegistered')}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {services.map((service) => (
              <div
                key={service.name}
                className={`rounded-xl border p-4 transition hover:border-sky-500/30 ${
                  service.state === ServiceState.ERROR
                    ? 'border-rose-500/30 bg-rose-500/5'
                    : 'border-slate-800 bg-slate-900/70'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    {getStateIcon(service.state)}
                    <div>
                      <p className="text-sm font-medium text-slate-100">{service.display_name}</p>
                      <p className="text-xs text-slate-500">{service.name}</p>
                    </div>
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${getStateBadgeClass(service.state)}`}>
                    {service.state}
                  </span>
                </div>

                {service.uptime_seconds !== null && service.state === ServiceState.RUNNING && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                    <Clock className="h-3.5 w-3.5" />
                    <span>{t('health.serviceDetails.uptime')}: {formatUptime(service.uptime_seconds)}</span>
                  </div>
                )}

                {service.error_count > 0 && (
                  <div className="mt-2 text-xs text-rose-400">
                    {t('health.serviceDetails.errorsLogged', { count: service.error_count })}
                  </div>
                )}

                {service.last_error && (
                  <div className="mt-2 text-xs text-rose-300 truncate" title={service.last_error}>
                    {t('health.serviceDetails.lastError')}: {service.last_error}
                  </div>
                )}

                {service.sample_count !== null && (
                  <div className="mt-2 text-xs text-slate-500">
                    {t('health.serviceDetails.samplesCollected', { count: service.sample_count })}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* System Stats */}
      {health && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
          {/* CPU Card */}
          <div className="card border-slate-800/40 bg-slate-900/60">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/20">
                <Cpu className="h-5 w-5 text-violet-400" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">CPU</p>
                <p className="text-lg font-semibold text-white">{health.system.cpu.usage.toFixed(1)}%</p>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-400">
              <p className="truncate" title={health.system.cpu.model}>{health.system.cpu.model}</p>
              <p>{health.system.cpu.cores} cores @ {(health.system.cpu.frequency_mhz / 1000).toFixed(2)} GHz</p>
              {health.system.cpu.temperature_celsius && (
                <p className="flex items-center gap-1">
                  <Thermometer className="h-3.5 w-3.5" />
                  {health.system.cpu.temperature_celsius.toFixed(1)}°C
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
                      : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                  }`}>
                    {device.status}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.capacity')}</p>
                    <p className="text-slate-200">{formatBytes(device.capacity_bytes)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.used')}</p>
                    <p className="text-slate-200">{device.used_percent.toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('health.deviceLabels.mount')}</p>
                    <p className="text-slate-200">{device.mount_point}</p>
                  </div>
                  {device.temperature !== null && (
                    <div>
                      <p className="text-slate-500">{t('health.deviceLabels.temperature')}</p>
                      <p className="text-slate-200">{device.temperature}°C</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
