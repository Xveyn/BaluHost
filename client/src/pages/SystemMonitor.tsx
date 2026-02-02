/**
 * System Monitor Page
 *
 * Consolidated monitoring view with tabs for:
 * - CPU (usage, frequency, temperature)
 * - RAM (usage, percent)
 * - Network (download/upload speeds)
 * - Disk I/O (per-disk throughput, IOPS)
 * - Power (from Tapo devices if available)
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MetricChart, TimeRangeSelector } from '../components/monitoring';
import type { TimeRange } from '../api/monitoring';
import { formatTimestamp } from '../lib/dateUtils';
import {
  useCpuMonitoring,
  useMemoryMonitoring,
  useNetworkMonitoring,
  useDiskIoMonitoring,
} from '../hooks/useMonitoring';
import { getPowerHistory } from '../api/power';
import type { PowerMonitoringResponse } from '../api/power';
import {
  getEnergyPriceConfig,
  updateEnergyPriceConfig,
  getCumulativeEnergy,
  type EnergyPriceConfig,
  type CumulativeEnergyResponse,
} from '../api/energy';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import toast from 'react-hot-toast';
import { ServicesTab } from '../components/services';
import { AdminBadge } from '../components/ui/AdminBadge';
import { BenchmarkPanel } from '../components/benchmark';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

interface SystemMonitorProps {
  user: User;
}

type TabType = 'cpu' | 'memory' | 'network' | 'disk-io' | 'power' | 'services';

interface TabConfig {
  id: TabType;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const TABS: TabConfig[] = [
  {
    id: 'cpu',
    label: 'CPU',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M9 9h6v6H9z" />
        <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'memory',
    label: 'RAM',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <path d="M6 10v4M10 10v4M14 10v4M18 10v4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'network',
    label: 'Netzwerk',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M5 12.55a11 11 0 0114.08 0M8.53 16.11a6 6 0 016.95 0M12 20h.01" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'disk-io',
    label: 'Disk I/O',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      </svg>
    ),
  },
  {
    id: 'power',
    label: 'Strom',
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'services',
    label: 'Services',
    adminOnly: true,
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" strokeLinecap="round" />
      </svg>
    ),
  },
];

// Format bytes to human readable
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// formatTimestamp is imported from ../lib/dateUtils

// StatCard component
interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
  color: string;
  icon: React.ReactNode;
}

function StatCard({ label, value, unit, color, icon }: StatCardProps) {
  return (
    <div className={`card border-slate-800/60 bg-gradient-to-br from-${color}-500/10 to-transparent p-3 sm:p-5`}>
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] sm:text-xs font-medium uppercase tracking-wider text-slate-400 truncate">{label}</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-semibold text-white">
            {value}
            {unit && <span className="ml-1 text-sm sm:text-lg text-slate-400">{unit}</span>}
          </p>
        </div>
        <div className={`rounded-full bg-${color}-500/20 p-2 sm:p-3 flex-shrink-0 ml-2`}>{icon}</div>
      </div>
    </div>
  );
}

// CPU Tab Component
function CpuTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useCpuMonitoring({ historyDuration: timeRange });
  const [viewMode, setViewMode] = useState<'overall' | 'per-thread'>('overall');

  const usageChartData = useMemo(() => {
    return history
      .filter((s) => s.usage_percent !== undefined && s.usage_percent >= 0)
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        usage: s.usage_percent,
      }));
  }, [history]);

  // Generate individual chart data for each thread (Task Manager style)
  const individualThreadCharts = useMemo(() => {
    if (viewMode !== 'per-thread' || !current?.thread_usages) return [];

    const pCores = current.p_core_count ?? 0;
    const eCores = current.e_core_count ?? 0;
    const totalThreads = current.thread_usages.length;
    const pThreadCount = pCores * 2; // P-cores have hyperthreading

    return current.thread_usages.map((currentUsage, idx) => {
      // Determine thread type
      let threadType: 'P' | 'E' | 'normal' = 'normal';
      let color = '#3b82f6'; // Default blue

      if (pCores > 0 || eCores > 0) {
        // Hybrid CPU
        if (idx < pThreadCount) {
          threadType = 'P';
          color = `hsl(${210 + (idx % 4) * 10}, 75%, ${60 + (idx % 3) * 8}%)`; // Blue spectrum
        } else {
          threadType = 'E';
          color = `hsl(${140 + (idx % 4) * 15}, 70%, ${55 + (idx % 3) * 8}%)`; // Green spectrum
        }
      } else {
        // Normal CPU - use rainbow spectrum
        const hue = (idx / totalThreads) * 360;
        color = `hsl(${hue}, 70%, 60%)`;
      }

      // Create chart data for this specific thread
      const chartData = history.map((sample) => ({
        time: formatTimestamp(sample.timestamp),
        usage: sample.thread_usages?.[idx] ?? 0,
      }));

      return {
        threadIndex: idx,
        threadType,
        color,
        currentUsage,
        chartData,
        label: threadType === 'normal'
          ? `CPU ${idx}`
          : `${threadType === 'P' ? 'P-Core' : 'E-Core'} ${idx}`,
      };
    });
  }, [history, viewMode, current]);

  // Check if this is a hybrid CPU
  const isHybridCpu = (current?.p_core_count ?? 0) > 0 || (current?.e_core_count ?? 0) > 0;

  const temperatureChartData = useMemo(() => {
    return history
      .filter((s) => s.temperature_celsius !== null && s.temperature_celsius !== undefined)
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        temperature: s.temperature_celsius,
      }));
  }, [history]);

  const hasTemperatureData = temperatureChartData.length > 0;

  // Build core info string
  const coreInfo = useMemo(() => {
    if (!current) return null;
    const cores = current.core_count ?? 0;
    const threads = current.thread_count ?? cores;
    const pCores = current.p_core_count;
    const eCores = current.e_core_count;

    // Debug: Log thread_usages to console
    if (current.thread_usages) {
      console.log('[CPU Monitor] Thread usages received:', current.thread_usages.length, 'threads');
    } else {
      console.log('[CPU Monitor] No thread_usages data received from backend');
    }

    // If we have P/E core info (Intel hybrid)
    if (pCores !== null && pCores !== undefined && eCores !== null && eCores !== undefined) {
      return {
        main: t('monitor.coresThreads', { cores, threads }),
        detail: `${pCores} ${t('monitor.pCores')}, ${eCores} ${t('monitor.eCores')}`,
        isHybrid: true,
      };
    }

    return {
      main: `${cores} ${t('monitor.cores')}`,
      detail: `${threads} ${t('monitor.threads')}`,
      isHybrid: false,
    };
  }, [current]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
        <StatCard
          label={t('monitor.cpuUsage')}
          value={current?.usage_percent?.toFixed(1) ?? '0'}
          unit="%"
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">%</span>}
        />
        <StatCard
          label={t('monitor.frequency')}
          value={current?.frequency_mhz ? (current.frequency_mhz / 1000).toFixed(2) : '-'}
          unit="GHz"
          color="purple"
          icon={<span className="text-purple-400 text-base sm:text-xl">~</span>}
        />
        <StatCard
          label={t('monitor.temperature')}
          value={current?.temperature_celsius?.toFixed(1) ?? '-'}
          unit="°C"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">🌡</span>}
        />
        {/* Cores & Threads Card */}
        <div className="card border-slate-800/60 bg-gradient-to-br from-green-500/10 to-transparent p-3 sm:p-5">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] sm:text-xs font-medium uppercase tracking-wider text-slate-400">{t('monitor.processor')}</p>
              <p className="mt-1 sm:mt-2 text-base sm:text-xl font-semibold text-white truncate">
                {coreInfo?.main ?? '-'}
              </p>
              {coreInfo?.detail && (
                <p className={`mt-0.5 sm:mt-1 text-xs sm:text-sm truncate ${coreInfo.isHybrid ? 'text-cyan-400' : 'text-slate-400'}`}>
                  {coreInfo.detail}
                </p>
              )}
            </div>
            <div className="rounded-full bg-green-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
              <span className="text-green-400 text-base sm:text-xl">#</span>
            </div>
          </div>
        </div>
      </div>

      {/* Usage Chart - Toggle Buttons */}
      <div className="flex items-center justify-between">
        <h3 className="text-base sm:text-lg font-semibold text-white">
          {viewMode === 'overall' ? t('monitor.cpuUsage') : t('monitor.cpuUsagePerThread')}
        </h3>
        {current?.thread_usages && current.thread_usages.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={() => setViewMode('overall')}
              className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                viewMode === 'overall'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              {t('monitor.overall')}
            </button>
            <button
              onClick={() => setViewMode('per-thread')}
              className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                viewMode === 'per-thread'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              {t('monitor.perThread')}
            </button>
          </div>
        )}
      </div>

      {/* Overall CPU Chart */}
      {viewMode === 'overall' && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <MetricChart
            data={usageChartData}
            lines={[{ dataKey: 'usage', name: t('monitor.usagePercent'), color: '#3b82f6' }]}
            yAxisLabel="%"
            yAxisDomain={[0, 100]}
            height={250}
            loading={loading}
            showArea
          />
        </div>
      )}

      {/* Per-Thread Charts - Task Manager Style Grid */}
      {viewMode === 'per-thread' && individualThreadCharts.length > 0 && (
        <>
          {/* P-Cores Section (for hybrid CPUs) */}
          {isHybridCpu && individualThreadCharts.some(tc => tc.threadType === 'P') && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-blue-500"></div>
                <h4 className="text-sm sm:text-base font-semibold text-white">
                  {t('monitor.pCoresPerformance')} - {t('monitor.coresThreadsCount', { cores: current?.p_core_count, threads: (current?.p_core_count ?? 0) * 2 })}
                </h4>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                {individualThreadCharts
                  .filter(thread => thread.threadType === 'P')
                  .map((thread) => (
                    <div
                      key={thread.threadIndex}
                      className="card border-slate-800/60 bg-gradient-to-br from-blue-500/5 to-transparent p-3"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                        <span className="text-xs font-bold text-blue-400">
                          {thread.currentUsage.toFixed(0)}%
                        </span>
                      </div>
                      <MetricChart
                        data={thread.chartData}
                        lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                        yAxisDomain={[0, 100]}
                        height={80}
                        loading={loading}
                        showArea
                        compact
                      />
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* E-Cores Section (for hybrid CPUs) */}
          {isHybridCpu && individualThreadCharts.some(tc => tc.threadType === 'E') && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-green-500"></div>
                <h4 className="text-sm sm:text-base font-semibold text-white">
                  {t('monitor.eCoresEfficiency')} - {t('monitor.coresThreadsCount', { cores: current?.e_core_count, threads: current?.e_core_count })}
                </h4>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                {individualThreadCharts
                  .filter(thread => thread.threadType === 'E')
                  .map((thread) => (
                    <div
                      key={thread.threadIndex}
                      className="card border-slate-800/60 bg-gradient-to-br from-green-500/5 to-transparent p-3"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                        <span className="text-xs font-bold text-green-400">
                          {thread.currentUsage.toFixed(0)}%
                        </span>
                      </div>
                      <MetricChart
                        data={thread.chartData}
                        lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                        yAxisDomain={[0, 100]}
                        height={80}
                        loading={loading}
                        showArea
                        compact
                      />
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* All Threads Section (for non-hybrid CPUs) */}
          {!isHybridCpu && (
            <div className="space-y-3">
              <h4 className="text-sm sm:text-base font-semibold text-white">
                {t('monitor.logicalProcessors')} ({individualThreadCharts.length})
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                {individualThreadCharts.map((thread) => (
                  <div
                    key={thread.threadIndex}
                    className="card border-slate-800/60 bg-slate-900/55 p-3"
                    style={{
                      background: `linear-gradient(to bottom right, ${thread.color}08, transparent)`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                      <span
                        className="text-xs font-bold"
                        style={{ color: thread.color }}
                      >
                        {thread.currentUsage.toFixed(0)}%
                      </span>
                    </div>
                    <MetricChart
                      data={thread.chartData}
                      lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                      yAxisDomain={[0, 100]}
                      height={80}
                      loading={loading}
                      showArea
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Temperature Chart - only show if data available */}
      {hasTemperatureData && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.cpuTemperature')}</h3>
          <MetricChart
            data={temperatureChartData}
            lines={[{ dataKey: 'temperature', name: t('monitor.temperatureUnit'), color: '#f97316' }]}
            yAxisLabel="°C"
            yAxisDomain={[0, 'auto']}
            height={250}
            loading={loading}
            showArea
          />
        </div>
      )}
    </div>
  );
}

// Memory Tab Component
function MemoryTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useMemoryMonitoring({ historyDuration: timeRange });

  // Calculate total RAM in GB for chart domain
  const totalGb = current ? current.total_bytes / (1024 * 1024 * 1024) : 16;

  // Filter out samples with invalid data and convert to GB
  const chartData = useMemo(() => {
    return history
      .filter((s) => s.used_bytes > 0 && s.total_bytes > 0) // Only valid samples
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        usedGb: s.used_bytes / (1024 * 1024 * 1024),
        baluhostGb: s.baluhost_memory_bytes && s.baluhost_memory_bytes > 0
          ? s.baluhost_memory_bytes / (1024 * 1024 * 1024)
          : null,
      }));
  }, [history]);

  const hasBaluhostData = chartData.some((d) => d.baluhostGb !== null);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-5">
        <StatCard
          label={t('monitor.used')}
          value={current ? formatBytes(current.used_bytes) : '-'}
          color="purple"
          icon={<span className="text-purple-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.total')}
          value={current ? formatBytes(current.total_bytes) : '-'}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">Σ</span>}
        />
        <StatCard
          label={t('monitor.available')}
          value={current?.available_bytes ? formatBytes(current.available_bytes) : '-'}
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">✓</span>}
        />
        <StatCard
          label={t('monitor.utilization')}
          value={current?.percent?.toFixed(1) ?? '0'}
          unit="%"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">%</span>}
        />
        <StatCard
          label="BaluHost"
          value={current?.baluhost_memory_bytes ? formatBytes(current.baluhost_memory_bytes) : '-'}
          color="cyan"
          icon={<span className="text-cyan-400 text-base sm:text-xl">🏠</span>}
        />
      </div>

      {/* Chart - Absolute values in GB */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.ramHistory')}</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'usedGb', name: t('monitor.usedGb'), color: '#a855f7' },
            ...(hasBaluhostData
              ? [{ dataKey: 'baluhostGb', name: t('monitor.baluhostGb'), color: '#06b6d4' }]
              : []),
          ]}
          yAxisLabel="GB"
          yAxisDomain={[0, Math.ceil(totalGb)]}
          height={300}
          loading={loading}
          showArea
        />
      </div>
    </div>
  );
}

// Network Tab Component
function NetworkTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useNetworkMonitoring({ historyDuration: timeRange });

  // Filter and map network data - only include valid samples
  const chartData = useMemo(() => {
    return history
      .filter((s) => s.download_mbps !== undefined && s.upload_mbps !== undefined)
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        download: s.download_mbps,
        upload: s.upload_mbps,
      }));
  }, [history]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('monitor.download')}
          value={current?.download_mbps?.toFixed(2) ?? '0'}
          unit="Mbit/s"
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">↓</span>}
        />
        <StatCard
          label={t('monitor.upload')}
          value={current?.upload_mbps?.toFixed(2) ?? '0'}
          unit="Mbit/s"
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">↑</span>}
        />
      </div>

      {/* Chart */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.networkHistory')}</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'download', name: t('monitor.downloadMbps'), color: '#3b82f6' },
            { dataKey: 'upload', name: t('monitor.uploadMbps'), color: '#10b981' },
          ]}
          yAxisLabel="Mbit/s"
          height={300}
          loading={loading}
        />
      </div>
    </div>
  );
}

// Disk I/O Tab Component
function DiskIoTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { disks, history, availableDisks, loading, error } = useDiskIoMonitoring({
    historyDuration: timeRange,
  });
  const [selectedDisk, setSelectedDisk] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'throughput' | 'iops'>('throughput');

  // Auto-select first disk
  useEffect(() => {
    if (!selectedDisk && availableDisks.length > 0) {
      setSelectedDisk(availableDisks[0]);
    }
  }, [availableDisks, selectedDisk]);

  const chartData = useMemo(() => {
    if (!selectedDisk || !history[selectedDisk]) return [];
    return history[selectedDisk]
      .filter((s) => s.read_mbps !== undefined && s.write_mbps !== undefined)
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        read: viewMode === 'throughput' ? s.read_mbps : s.read_iops,
        write: viewMode === 'throughput' ? s.write_mbps : s.write_iops,
      }));
  }, [selectedDisk, history, viewMode]);

  const currentDisk = selectedDisk ? disks[selectedDisk] : null;

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Disk Selector */}
      {availableDisks.length > 0 && (
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="flex gap-2 sm:gap-3 sm:flex-wrap min-w-max sm:min-w-0">
            {availableDisks.map((disk) => (
              <button
                key={disk}
                onClick={() => setSelectedDisk(disk)}
                className={`whitespace-nowrap rounded-lg border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  selectedDisk === disk
                    ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                    : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800'
                }`}
              >
                {disk}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Current Stats */}
      {selectedDisk && (
        <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-6">
          <StatCard
            label={t('monitor.read')}
            value={currentDisk?.read_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="blue"
            icon={<span className="text-blue-400 text-base sm:text-xl">📖</span>}
          />
          <StatCard
            label={t('monitor.write')}
            value={currentDisk?.write_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="green"
            icon={<span className="text-green-400 text-base sm:text-xl">✏️</span>}
          />
          <StatCard
            label={t('monitor.readIops')}
            value={currentDisk?.read_iops?.toFixed(0) ?? '0'}
            color="purple"
            icon={<span className="text-purple-400 text-base sm:text-xl">⚡</span>}
          />
          <StatCard
            label={t('monitor.writeIops')}
            value={currentDisk?.write_iops?.toFixed(0) ?? '0'}
            color="orange"
            icon={<span className="text-orange-400 text-base sm:text-xl">⚡</span>}
          />
          <StatCard
            label={t('monitor.responseTime')}
            value={currentDisk?.avg_response_ms?.toFixed(2) ?? '-'}
            unit="ms"
            color="cyan"
            icon={<span className="text-cyan-400 text-base sm:text-xl">⏱</span>}
          />
          <StatCard
            label={t('monitor.activeTime')}
            value={currentDisk?.active_time_percent?.toFixed(1) ?? '-'}
            unit="%"
            color="teal"
            icon={<span className="text-teal-400 text-base sm:text-xl">📊</span>}
          />
        </div>
      )}

      {/* Chart */}
      {selectedDisk && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <h3 className="text-base sm:text-lg font-semibold text-white">{selectedDisk} - {t('monitor.history')}</h3>
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('throughput')}
                className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  viewMode === 'throughput'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {t('monitor.throughput')}
              </button>
              <button
                onClick={() => setViewMode('iops')}
                className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  viewMode === 'iops'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {t('monitor.iops')}
              </button>
            </div>
          </div>
          <MetricChart
            data={chartData}
            lines={[
              {
                dataKey: 'read',
                name: viewMode === 'throughput' ? t('monitor.readMbs') : t('monitor.readIops'),
                color: '#3b82f6',
              },
              {
                dataKey: 'write',
                name: viewMode === 'throughput' ? t('monitor.writeMbs') : t('monitor.writeIops'),
                color: '#10b981',
              },
            ]}
            yAxisLabel={viewMode === 'throughput' ? 'MB/s' : 'IOPS'}
            height={300}
            loading={loading}
          />
        </div>
      )}

      {availableDisks.length === 0 && !loading && (
        <div className="text-center py-8 sm:py-12 text-slate-400">
          <p>{t('monitor.noDisksDetected')}</p>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">{t('monitor.waitingForData')}</p>
        </div>
      )}

      {/* Disk Benchmark Section */}
      <div className="border-t border-slate-800 pt-6 mt-6">
        <BenchmarkPanel />
      </div>
    </div>
  );
}

// Power Tab Component
type CumulativePeriod = 'today' | 'week' | 'month';

function PowerTab() {
  const { t } = useTranslation(['system', 'common']);
  const [powerData, setPowerData] = useState<PowerMonitoringResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Energy price config state
  const [priceConfig, setPriceConfig] = useState<EnergyPriceConfig | null>(null);
  const [editingPrice, setEditingPrice] = useState(false);
  const [priceInput, setPriceInput] = useState('');
  const [savingPrice, setSavingPrice] = useState(false);

  // Cumulative energy state
  const [cumulativePeriod, setCumulativePeriod] = useState<CumulativePeriod>('today');
  const [cumulativeData, setCumulativeData] = useState<CumulativeEnergyResponse | null>(null);
  const [cumulativeLoading, setCumulativeLoading] = useState(false);

  const fetchPower = useCallback(async () => {
    try {
      const data = await getPowerHistory();
      setPowerData(data);
      setError(null);
    } catch (err: any) {
      // Don't show error for no devices configured
      if (err.response?.status !== 404) {
        setError(err.message || 'Failed to load power data');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch price config on mount
  useEffect(() => {
    const fetchPriceConfig = async () => {
      try {
        const config = await getEnergyPriceConfig();
        setPriceConfig(config);
        setPriceInput(config.cost_per_kwh.toString());
      } catch (err) {
        console.error('Failed to load price config:', err);
      }
    };
    fetchPriceConfig();
  }, []);

  // Fetch cumulative data when period changes or power data updates
  useEffect(() => {
    const fetchCumulative = async () => {
      if (!powerData || powerData.devices.length === 0) return;

      setCumulativeLoading(true);
      try {
        // Use first device for now
        const deviceId = powerData.devices[0].device_id;
        const data = await getCumulativeEnergy(deviceId, cumulativePeriod);
        setCumulativeData(data);
      } catch (err) {
        console.error('Failed to load cumulative data:', err);
      } finally {
        setCumulativeLoading(false);
      }
    };
    fetchCumulative();
  }, [powerData, cumulativePeriod]);

  const handleSavePrice = async () => {
    const newPrice = parseFloat(priceInput);
    if (isNaN(newPrice) || newPrice < 0.01 || newPrice > 10.0) {
      toast.error(t('monitor.power.priceMustBeBetween'));
      return;
    }

    setSavingPrice(true);
    try {
      const updated = await updateEnergyPriceConfig({
        cost_per_kwh: newPrice,
        currency: priceConfig?.currency || 'EUR',
      });
      setPriceConfig(updated);
      setEditingPrice(false);
      toast.success(t('monitor.power.priceUpdated'));
      // Refresh cumulative data with new price
      if (powerData && powerData.devices.length > 0) {
        const data = await getCumulativeEnergy(powerData.devices[0].device_id, cumulativePeriod);
        setCumulativeData(data);
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || t('monitor.power.saveError'));
    } finally {
      setSavingPrice(false);
    }
  };

  useEffect(() => {
    fetchPower();
    const interval = setInterval(fetchPower, 5000);
    return () => clearInterval(interval);
  }, [fetchPower]);

  // Calculate cumulative energy consumption from samples
  const calculateCumulativeEnergy = useCallback((samples: { timestamp: string; watts: number }[]) => {
    if (samples.length < 2) return 0;

    let totalWh = 0;
    for (let i = 1; i < samples.length; i++) {
      const prevTime = new Date(samples[i - 1].timestamp).getTime();
      const currTime = new Date(samples[i].timestamp).getTime();
      const hours = (currTime - prevTime) / (1000 * 60 * 60);
      const avgWatts = (samples[i - 1].watts + samples[i].watts) / 2;
      totalWh += avgWatts * hours;
    }
    return totalWh / 1000; // Convert Wh to kWh
  }, []);

  // Calculate total cumulative energy across all devices
  const totalCumulativeEnergy = useMemo(() => {
    if (!powerData) return 0;
    return powerData.devices.reduce((sum, device) => {
      return sum + calculateCumulativeEnergy(device.samples);
    }, 0);
  }, [powerData, calculateCumulativeEnergy]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
      </div>
    );
  }

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  if (!powerData || powerData.devices.length === 0) {
    return (
      <div className="text-center py-12">
        <svg
          className="mx-auto h-16 w-16 text-slate-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-9z"
          />
        </svg>
        <p className="mt-4 text-slate-400">{t('monitor.power.noTapoDevices')}</p>
        <p className="text-sm text-slate-500 mt-1">
          {t('monitor.power.configureTapoDevice')}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Total Power Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
        <StatCard
          label={t('monitor.power.currentPower')}
          value={powerData.total_current_power.toFixed(1)}
          unit="W"
          color="yellow"
          icon={<span className="text-yellow-400 text-base sm:text-xl">⚡</span>}
        />
        <StatCard
          label={t('monitor.power.cumulativeSession')}
          value={totalCumulativeEnergy.toFixed(4)}
          unit="kWh"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">Σ</span>}
        />
        <StatCard
          label={t('monitor.power.todayTotal')}
          value={powerData.devices.reduce((sum, d) => sum + (d.latest_sample?.energy_today ?? 0), 0).toFixed(2)}
          unit="kWh"
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.power.devices')}
          value={powerData.devices.length}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">#</span>}
        />
      </div>

      {/* Per-device stats */}
      {powerData.devices.map((device) => {
        const deviceCumulativeEnergy = calculateCumulativeEnergy(device.samples);

        return (
          <div key={device.device_id} className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
            <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{device.device_name}</h3>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.powerLabel')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.watts?.toFixed(1) ?? '-'} <span className="text-sm sm:text-base text-slate-400">W</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.voltage')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.voltage?.toFixed(1) ?? '-'} <span className="text-sm sm:text-base text-slate-400">V</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.current')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.current?.toFixed(3) ?? '-'} <span className="text-sm sm:text-base text-slate-400">A</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.today')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.energy_today?.toFixed(2) ?? '-'} <span className="text-sm sm:text-base text-slate-400">kWh</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.cumulativeSession')}</p>
                <p className="text-lg sm:text-xl font-semibold text-orange-400">
                  {deviceCumulativeEnergy.toFixed(4)} <span className="text-sm sm:text-base text-slate-400">kWh</span>
                </p>
              </div>
            </div>

            {/* Mini chart for this device */}
            {device.samples.length > 0 && (
              <div className="mt-3 sm:mt-4">
                <MetricChart
                  data={device.samples.map((s) => ({
                    time: formatTimestamp(s.timestamp),
                    watts: s.watts,
                  }))}
                  lines={[{ dataKey: 'watts', name: t('monitor.power.powerWatts'), color: '#eab308' }]}
                  height={180}
                  showArea
                />
              </div>
            )}
          </div>
        );
      })}

      {/* Cumulative Energy Chart Section */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        {/* Header with Price Config */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-base sm:text-lg font-semibold text-white">
              {t('monitor.power.cumulativeConsumptionCosts')}
            </h3>
            {priceConfig && (
              <div className="flex items-center gap-2">
                {editingPrice ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="10"
                      value={priceInput}
                      onChange={(e) => setPriceInput(e.target.value)}
                      className="w-20 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
                      disabled={savingPrice}
                    />
                    <span className="text-slate-400 text-sm">{priceConfig.currency}/kWh</span>
                    <button
                      onClick={handleSavePrice}
                      disabled={savingPrice}
                      className="px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
                    >
                      {savingPrice ? '...' : '✓'}
                    </button>
                    <button
                      onClick={() => {
                        setEditingPrice(false);
                        setPriceInput(priceConfig.cost_per_kwh.toString());
                      }}
                      disabled={savingPrice}
                      className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditingPrice(true)}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700"
                  >
                    <span>{priceConfig.cost_per_kwh.toFixed(2)} {priceConfig.currency}/kWh</span>
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Period Selector */}
          <div className="flex gap-1 sm:gap-2">
            {(['today', 'week', 'month'] as CumulativePeriod[]).map((period) => (
              <button
                key={period}
                onClick={() => setCumulativePeriod(period)}
                className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
                  cumulativePeriod === period
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
                }`}
              >
                {period === 'today' ? t('monitor.power.periodToday') : period === 'week' ? t('monitor.power.periodWeek') : t('monitor.power.periodMonth')}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        {cumulativeData && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.totalConsumption')}</p>
              <p className="text-lg font-semibold text-emerald-400">
                {cumulativeData.total_kwh.toFixed(3)} <span className="text-sm text-slate-400">kWh</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.totalCosts')}</p>
              <p className="text-lg font-semibold text-orange-400">
                {cumulativeData.total_cost.toFixed(2)} <span className="text-sm text-slate-400">{cumulativeData.currency}</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.electricityPrice')}</p>
              <p className="text-lg font-semibold text-slate-300">
                {cumulativeData.cost_per_kwh.toFixed(2)} <span className="text-sm text-slate-400">{cumulativeData.currency}/kWh</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.dataPoints')}</p>
              <p className="text-lg font-semibold text-slate-300">
                {cumulativeData.data_points.length}
              </p>
            </div>
          </div>
        )}

        {/* Chart */}
        {cumulativeLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
          </div>
        ) : cumulativeData && cumulativeData.data_points.length > 0 ? (
          <div className="h-[300px] sm:h-[350px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={cumulativeData.data_points.map((dp) => ({
                  time: new Date(dp.timestamp).toLocaleTimeString('de-DE', {
                    hour: '2-digit',
                    minute: '2-digit',
                  }),
                  fullTime: new Date(dp.timestamp).toLocaleString('de-DE'),
                  kwh: dp.cumulative_kwh,
                  cost: dp.cumulative_cost,
                  watts: dp.instant_watts,
                }))}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="colorKwh" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="time"
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="left"
                  stroke="#10b981"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v.toFixed(2)}`}
                  label={{ value: 'kWh', angle: -90, position: 'insideLeft', fill: '#10b981', fontSize: 11 }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#f97316"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v.toFixed(2)}`}
                  label={{ value: cumulativeData.currency, angle: 90, position: 'insideRight', fill: '#f97316', fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  labelStyle={{ color: '#94a3b8' }}
                  formatter={(value: number, name: string) => {
                    if (name === 'kwh') return [`${value.toFixed(4)} kWh`, t('monitor.power.consumption')];
                    if (name === 'cost') return [`${value.toFixed(4)} ${cumulativeData.currency}`, t('monitor.power.costsLabel')];
                    if (name === 'watts') return [`${value.toFixed(1)} W`, t('monitor.power.powerLabel')];
                    return [value, name];
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      return payload[0].payload.fullTime;
                    }
                    return label;
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: '12px' }}
                  formatter={(value) => {
                    if (value === 'kwh') return t('monitor.power.consumptionKwh');
                    if (value === 'cost') return `${t('monitor.power.costsLabel')} (${cumulativeData.currency})`;
                    return value;
                  }}
                />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="kwh"
                  stroke="#10b981"
                  strokeWidth={2}
                  fill="url(#colorKwh)"
                  name="kwh"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="cost"
                  stroke="#f97316"
                  strokeWidth={2}
                  dot={false}
                  name="cost"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-center py-8 text-slate-400">
            {t('monitor.noDataForPeriod')}
          </div>
        )}
      </div>
    </div>
  );
}

// Main Component
export default function SystemMonitor({ user }: SystemMonitorProps) {
  const { t } = useTranslation(['system', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');

  const isAdmin = user?.role === 'admin';

  // Get active tab from URL, default to 'cpu'
  const activeTab = (searchParams.get('tab') || 'cpu') as TabType;

  // Tab change handler that updates URL
  const handleTabChange = (tab: TabType) => {
    setSearchParams({ tab });
  };

  // Filter tabs based on admin status
  const visibleTabs = useMemo(() => {
    return TABS.filter(tab => !tab.adminOnly || isAdmin);
  }, [isAdmin]);

  // Translate tab labels
  const getTabLabel = (tabId: TabType): string => {
    const tabKeyMap: Record<TabType, string> = {
      'cpu': 'monitor.tabs.cpu',
      'memory': 'monitor.tabs.memory',
      'network': 'monitor.tabs.network',
      'disk-io': 'monitor.tabs.diskIo',
      'power': 'monitor.tabs.power',
      'services': 'monitor.tabs.services',
    };
    return t(tabKeyMap[tabId]);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('monitor.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('monitor.subtitleLong')}
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <div className="rounded-full border border-slate-800 bg-slate-900/70 px-3 sm:px-4 py-1.5 sm:py-2 text-xs text-slate-400 shadow-inner">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400 inline-block mr-2" />
            {t('monitor.live')}
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                activeTab === tab.id
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
              }`}
            >
              {tab.icon}
              <span className="hidden sm:inline">{getTabLabel(tab.id)}</span>
              <span className="sm:hidden">{getTabLabel(tab.id).slice(0, 3)}</span>
              {tab.adminOnly && <AdminBadge />}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'cpu' && <CpuTab timeRange={timeRange} />}
        {activeTab === 'memory' && <MemoryTab timeRange={timeRange} />}
        {activeTab === 'network' && <NetworkTab timeRange={timeRange} />}
        {activeTab === 'disk-io' && <DiskIoTab timeRange={timeRange} />}
        {activeTab === 'power' && <PowerTab />}
        {activeTab === 'services' && <ServicesTab isAdmin={isAdmin} />}
      </div>
    </div>
  );
}
