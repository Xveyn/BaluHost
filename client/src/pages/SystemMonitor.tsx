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
import { MetricChart, TimeRangeSelector } from '../components/monitoring';
import type { TimeRange } from '../api/monitoring';
import {
  useCpuMonitoring,
  useMemoryMonitoring,
  useNetworkMonitoring,
  useDiskIoMonitoring,
} from '../hooks/useMonitoring';
import { getPowerHistory } from '../api/power';
import type { PowerMonitoringResponse } from '../api/power';

type TabType = 'cpu' | 'memory' | 'network' | 'disk-io' | 'power';

interface TabConfig {
  id: TabType;
  label: string;
  icon: React.ReactNode;
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
];

// Format bytes to human readable
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// Format timestamp for chart
const formatTimestamp = (ts: string): string => {
  const date = new Date(ts);
  return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

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
    <div className={`card border-slate-800/60 bg-gradient-to-br from-${color}-500/10 to-transparent p-5`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-white">
            {value}
            {unit && <span className="ml-1 text-lg text-slate-400">{unit}</span>}
          </p>
        </div>
        <div className={`rounded-full bg-${color}-500/20 p-3`}>{icon}</div>
      </div>
    </div>
  );
}

// CPU Tab Component
function CpuTab({ timeRange }: { timeRange: TimeRange }) {
  const { current, history, loading, error } = useCpuMonitoring({ historyDuration: timeRange });

  const usageChartData = useMemo(() => {
    return history.map((s) => ({
      time: formatTimestamp(s.timestamp),
      usage: s.usage_percent,
    }));
  }, [history]);

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

    // If we have P/E core info (Intel hybrid)
    if (pCores !== null && pCores !== undefined && eCores !== null && eCores !== undefined) {
      return {
        main: `${cores} Kerne / ${threads} Threads`,
        detail: `${pCores} P-Cores, ${eCores} E-Cores`,
        isHybrid: true,
      };
    }

    return {
      main: `${cores} Kerne`,
      detail: `${threads} Threads`,
      isHybrid: false,
    };
  }, [current]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="CPU-Auslastung"
          value={current?.usage_percent?.toFixed(1) ?? '0'}
          unit="%"
          color="blue"
          icon={<span className="text-blue-400 text-xl">%</span>}
        />
        <StatCard
          label="Frequenz"
          value={current?.frequency_mhz ? (current.frequency_mhz / 1000).toFixed(2) : '-'}
          unit="GHz"
          color="purple"
          icon={<span className="text-purple-400 text-xl">~</span>}
        />
        <StatCard
          label="Temperatur"
          value={current?.temperature_celsius?.toFixed(1) ?? '-'}
          unit="°C"
          color="orange"
          icon={<span className="text-orange-400 text-xl">🌡</span>}
        />
        {/* Cores & Threads Card */}
        <div className="card border-slate-800/60 bg-gradient-to-br from-green-500/10 to-transparent p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Prozessor</p>
              <p className="mt-2 text-xl font-semibold text-white">
                {coreInfo?.main ?? '-'}
              </p>
              {coreInfo?.detail && (
                <p className={`mt-1 text-sm ${coreInfo.isHybrid ? 'text-cyan-400' : 'text-slate-400'}`}>
                  {coreInfo.detail}
                </p>
              )}
            </div>
            <div className="rounded-full bg-green-500/20 p-3">
              <span className="text-green-400 text-xl">#</span>
            </div>
          </div>
        </div>
      </div>

      {/* Usage Chart */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">CPU-Auslastung</h3>
        <MetricChart
          data={usageChartData}
          lines={[{ dataKey: 'usage', name: 'Auslastung (%)', color: '#3b82f6' }]}
          yAxisLabel="%"
          yAxisDomain={[0, 100]}
          height={300}
          loading={loading}
          showArea
        />
      </div>

      {/* Temperature Chart - only show if data available */}
      {hasTemperatureData && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-6">
          <h3 className="mb-4 text-lg font-semibold text-white">CPU-Temperatur</h3>
          <MetricChart
            data={temperatureChartData}
            lines={[{ dataKey: 'temperature', name: 'Temperatur (°C)', color: '#f97316' }]}
            yAxisLabel="°C"
            yAxisDomain={[0, 'auto']}
            height={300}
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
  const { current, history, loading, error } = useMemoryMonitoring({ historyDuration: timeRange });

  // Calculate total RAM in GB for chart domain
  const totalGb = current ? current.total_bytes / (1024 * 1024 * 1024) : 16;

  const chartData = useMemo(() => {
    return history.map((s) => ({
      time: formatTimestamp(s.timestamp),
      usedGb: s.used_bytes / (1024 * 1024 * 1024),
      baluhostGb: s.baluhost_memory_bytes
        ? s.baluhost_memory_bytes / (1024 * 1024 * 1024)
        : null,
    }));
  }, [history]);

  const hasBaluhostData = chartData.some((d) => d.baluhostGb !== null);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Belegt"
          value={current ? formatBytes(current.used_bytes) : '-'}
          color="purple"
          icon={<span className="text-purple-400 text-xl">📊</span>}
        />
        <StatCard
          label="Gesamt"
          value={current ? formatBytes(current.total_bytes) : '-'}
          color="blue"
          icon={<span className="text-blue-400 text-xl">Σ</span>}
        />
        <StatCard
          label="Verfügbar"
          value={current?.available_bytes ? formatBytes(current.available_bytes) : '-'}
          color="green"
          icon={<span className="text-green-400 text-xl">✓</span>}
        />
        <StatCard
          label="Auslastung"
          value={current?.percent?.toFixed(1) ?? '0'}
          unit="%"
          color="orange"
          icon={<span className="text-orange-400 text-xl">%</span>}
        />
        <StatCard
          label="BaluHost"
          value={current?.baluhost_memory_bytes ? formatBytes(current.baluhost_memory_bytes) : '-'}
          color="cyan"
          icon={<span className="text-cyan-400 text-xl">🏠</span>}
        />
      </div>

      {/* Chart - Absolute values in GB */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">RAM-Verlauf (absolut)</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'usedGb', name: 'Belegt (GB)', color: '#a855f7' },
            ...(hasBaluhostData
              ? [{ dataKey: 'baluhostGb', name: 'BaluHost (GB)', color: '#06b6d4' }]
              : []),
          ]}
          yAxisLabel="GB"
          yAxisDomain={[0, Math.ceil(totalGb)]}
          height={350}
          loading={loading}
          showArea
        />
      </div>
    </div>
  );
}

// Network Tab Component
function NetworkTab({ timeRange }: { timeRange: TimeRange }) {
  const { current, history, loading, error } = useNetworkMonitoring({ historyDuration: timeRange });

  const chartData = useMemo(() => {
    return history.map((s) => ({
      time: formatTimestamp(s.timestamp),
      download: s.download_mbps,
      upload: s.upload_mbps,
    }));
  }, [history]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <StatCard
          label="Download"
          value={current?.download_mbps?.toFixed(2) ?? '0'}
          unit="Mbit/s"
          color="blue"
          icon={<span className="text-blue-400 text-xl">↓</span>}
        />
        <StatCard
          label="Upload"
          value={current?.upload_mbps?.toFixed(2) ?? '0'}
          unit="Mbit/s"
          color="green"
          icon={<span className="text-green-400 text-xl">↑</span>}
        />
      </div>

      {/* Chart */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">Netzwerk-Verlauf</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'download', name: 'Download (Mbit/s)', color: '#3b82f6' },
            { dataKey: 'upload', name: 'Upload (Mbit/s)', color: '#10b981' },
          ]}
          yAxisLabel="Mbit/s"
          height={350}
          loading={loading}
        />
      </div>
    </div>
  );
}

// Disk I/O Tab Component
function DiskIoTab({ timeRange }: { timeRange: TimeRange }) {
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
    return history[selectedDisk].map((s) => ({
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
    <div className="space-y-6">
      {/* Disk Selector */}
      {availableDisks.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {availableDisks.map((disk) => (
            <button
              key={disk}
              onClick={() => setSelectedDisk(disk)}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-all ${
                selectedDisk === disk
                  ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                  : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              {disk}
            </button>
          ))}
        </div>
      )}

      {/* Current Stats */}
      {selectedDisk && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-6">
          <StatCard
            label="Lesen"
            value={currentDisk?.read_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="blue"
            icon={<span className="text-blue-400 text-xl">📖</span>}
          />
          <StatCard
            label="Schreiben"
            value={currentDisk?.write_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="green"
            icon={<span className="text-green-400 text-xl">✏️</span>}
          />
          <StatCard
            label="Lese-IOPS"
            value={currentDisk?.read_iops?.toFixed(0) ?? '0'}
            color="purple"
            icon={<span className="text-purple-400 text-xl">⚡</span>}
          />
          <StatCard
            label="Schreib-IOPS"
            value={currentDisk?.write_iops?.toFixed(0) ?? '0'}
            color="orange"
            icon={<span className="text-orange-400 text-xl">⚡</span>}
          />
          <StatCard
            label="Antwortzeit"
            value={currentDisk?.avg_response_ms?.toFixed(2) ?? '-'}
            unit="ms"
            color="cyan"
            icon={<span className="text-cyan-400 text-xl">⏱</span>}
          />
          <StatCard
            label="Aktive Zeit"
            value={currentDisk?.active_time_percent?.toFixed(1) ?? '-'}
            unit="%"
            color="teal"
            icon={<span className="text-teal-400 text-xl">📊</span>}
          />
        </div>
      )}

      {/* Chart */}
      {selectedDisk && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">{selectedDisk} - Verlauf</h3>
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('throughput')}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  viewMode === 'throughput'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                Durchsatz
              </button>
              <button
                onClick={() => setViewMode('iops')}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  viewMode === 'iops'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                IOPS
              </button>
            </div>
          </div>
          <MetricChart
            data={chartData}
            lines={[
              {
                dataKey: 'read',
                name: viewMode === 'throughput' ? 'Lesen (MB/s)' : 'Lese-IOPS',
                color: '#3b82f6',
              },
              {
                dataKey: 'write',
                name: viewMode === 'throughput' ? 'Schreiben (MB/s)' : 'Schreib-IOPS',
                color: '#10b981',
              },
            ]}
            yAxisLabel={viewMode === 'throughput' ? 'MB/s' : 'IOPS'}
            height={350}
            loading={loading}
          />
        </div>
      )}

      {availableDisks.length === 0 && !loading && (
        <div className="text-center py-12 text-slate-400">
          <p>Keine Festplatten erkannt</p>
          <p className="text-sm text-slate-500 mt-1">Warte auf erste Messung...</p>
        </div>
      )}
    </div>
  );
}

// Power Tab Component
function PowerTab() {
  const [powerData, setPowerData] = useState<PowerMonitoringResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    fetchPower();
    const interval = setInterval(fetchPower, 5000);
    return () => clearInterval(interval);
  }, [fetchPower]);

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
        <p className="mt-4 text-slate-400">Keine Tapo-Geräte konfiguriert</p>
        <p className="text-sm text-slate-500 mt-1">
          Konfigurieren Sie ein Tapo-Gerät in den Einstellungen, um den Stromverbrauch zu überwachen.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Total Power */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <StatCard
          label="Gesamtverbrauch"
          value={powerData.total_current_power.toFixed(1)}
          unit="W"
          color="yellow"
          icon={<span className="text-yellow-400 text-xl">⚡</span>}
        />
        <StatCard
          label="Geräte"
          value={powerData.devices.length}
          color="blue"
          icon={<span className="text-blue-400 text-xl">#</span>}
        />
      </div>

      {/* Per-device stats */}
      {powerData.devices.map((device) => (
        <div key={device.device_id} className="card border-slate-800/60 bg-slate-900/55 p-6">
          <h3 className="mb-4 text-lg font-semibold text-white">{device.device_name}</h3>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-slate-400">Leistung</p>
              <p className="text-xl font-semibold text-white">
                {device.latest_sample?.watts?.toFixed(1) ?? '-'} W
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Spannung</p>
              <p className="text-xl font-semibold text-white">
                {device.latest_sample?.voltage?.toFixed(1) ?? '-'} V
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Strom</p>
              <p className="text-xl font-semibold text-white">
                {device.latest_sample?.current?.toFixed(3) ?? '-'} A
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Heute</p>
              <p className="text-xl font-semibold text-white">
                {device.latest_sample?.energy_today?.toFixed(2) ?? '-'} kWh
              </p>
            </div>
          </div>

          {/* Mini chart for this device */}
          {device.samples.length > 0 && (
            <div className="mt-4">
              <MetricChart
                data={device.samples.map((s) => ({
                  time: formatTimestamp(s.timestamp),
                  watts: s.watts,
                }))}
                lines={[{ dataKey: 'watts', name: 'Leistung (W)', color: '#eab308' }]}
                height={200}
                showArea
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Main Component
export default function SystemMonitor() {
  const [activeTab, setActiveTab] = useState<TabType>('cpu');
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">System Monitor</h1>
          <p className="mt-1 text-sm text-slate-400">
            Echtzeit-Überwachung von CPU, RAM, Netzwerk, Festplatten und Stromverbrauch
          </p>
        </div>
        <div className="flex items-center gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <div className="rounded-full border border-slate-800 bg-slate-900/70 px-4 py-2 text-xs text-slate-400 shadow-inner">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400 inline-block mr-2" />
            Live
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-3">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'cpu' && <CpuTab timeRange={timeRange} />}
        {activeTab === 'memory' && <MemoryTab timeRange={timeRange} />}
        {activeTab === 'network' && <NetworkTab timeRange={timeRange} />}
        {activeTab === 'disk-io' && <DiskIoTab timeRange={timeRange} />}
        {activeTab === 'power' && <PowerTab />}
      </div>
    </div>
  );
}
