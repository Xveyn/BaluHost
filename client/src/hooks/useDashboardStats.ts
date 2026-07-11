import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { SystemInfoResponse, TelemetryHistory } from '../api/system';
import type { SmartStatusResponse } from '../api/smart';
import { detectCpuVendor, type Vendor } from '../components/dashboard/CpuGpuPanel';
import { formatNumber } from '../lib/formatters';

export type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';
export interface Delta { label: string; tone: DeltaTone; }
export interface SystemStats { cpuUsage: number; cpuCores: number; memoryUsed: number; memoryTotal: number; uptime: number; systemUptime: number; }
export interface StorageStats { used: number; total: number; available: number; percent: number; }
export interface CpuStatBase { vendor: Vendor; usagePercent: number; meta: string; submeta?: string; delta: Delta; tempC: number | null; }
export interface UseDashboardStatsInput {
  systemInfo: SystemInfoResponse | null;
  storageInfo: { total: number; used: number } | null;
  smartData: SmartStatusResponse | null;
  history: TelemetryHistory;
}
export interface UseDashboardStatsResult {
  systemStats: SystemStats; storageStats: StorageStats; memoryPercent: number;
  memorySpeedType: string | null; cpuStatBase: CpuStatBase;
  memoryDelta: Delta; storageDelta: Delta;
}

function formatDelta(value: number | null, suffix = '%'): Delta {
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
}

export function useDashboardStats({ systemInfo, storageInfo, smartData, history }: UseDashboardStatsInput): UseDashboardStatsResult {
  const { t } = useTranslation('dashboard');

  const systemStats = useMemo<SystemStats>(() => {
    const cpuUsage = Math.max(0, Math.min(systemInfo?.cpu.usage ?? 0, 100));
    const cpuCores = systemInfo?.cpu.cores ?? 0;
    const memoryUsed = systemInfo?.memory.used ?? 0;
    const memoryTotal = systemInfo?.memory.total ?? 0;
    const uptime = systemInfo?.uptime ?? 0;
    const systemUptime = systemInfo?.system_uptime ?? systemInfo?.uptime ?? 0;

    return { cpuUsage, cpuCores, memoryUsed, memoryTotal, uptime, systemUptime };
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

  const memoryDeltaRaw = useMemo(() => {
    const points = history.memory;
    if (points.length < 2) {
      return null;
    }
    const latest = points[points.length - 1]?.percent ?? 0;
    const previous = points[points.length - 2]?.percent ?? latest;
    return latest - previous;
  }, [history.memory]);

  const cpuFrequency = useMemo(() => {
    return systemInfo?.cpu?.frequency_mhz
      ? `${formatNumber(systemInfo.cpu.frequency_mhz / 1000, 2)} GHz`
      : null;
  }, [systemInfo]);

  const cpuTemperature = useMemo(() => {
    const temp = systemInfo?.cpu?.temperature_celsius;
    return typeof temp === 'number' ? `${formatNumber(temp, 1)}°C` : null;
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

  const cpuTempC = systemInfo?.cpu?.temperature_celsius ?? null;
  const cpuStatBase = useMemo<CpuStatBase>(() => ({
    vendor: detectCpuVendor(cpuModel),
    usagePercent: systemStats.cpuUsage,
    meta: cpuModel
      ? cpuModel
      : (cpuFrequency
        ? t('stats.coresAt', { count: systemStats.cpuCores || 0, frequency: cpuFrequency }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')
        : t('stats.coresActive', { count: systemStats.cpuCores || 0 }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')),
    submeta: cpuModel && cpuFrequency
      ? t('stats.coresAt', { count: systemStats.cpuCores || 0, frequency: cpuFrequency }) + (cpuTemperature ? ` • ${cpuTemperature}` : '')
      : undefined,
    delta: formatDelta(cpuDelta),
    tempC: cpuTempC,
  }), [systemStats.cpuUsage, systemStats.cpuCores, cpuModel, cpuFrequency, cpuTemperature, cpuTempC, cpuDelta, t]);

  return {
    systemStats,
    storageStats,
    memoryPercent,
    memorySpeedType,
    cpuStatBase,
    memoryDelta: formatDelta(memoryDeltaRaw),
    storageDelta: formatDelta(null),
  };
}
