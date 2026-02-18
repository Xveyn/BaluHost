import { useEffect, useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getCpuHistory,
  getMemoryHistory,
  getNetworkHistory,
  getDiskIoHistory,
} from '../../api/monitoring'
import type {
  CpuHistoryResponse,
  MemoryHistoryResponse,
  NetworkHistoryResponse,
  DiskIoHistoryResponse,
  TimeRange,
} from '../../api/monitoring'
import { formatNumber } from '../../lib/formatters'
import { RefreshCw, Cpu, MemoryStick, Network, HardDrive, TrendingDown, TrendingUp, Activity } from 'lucide-react'
import { MetricChart, TimeRangeSelector } from '../monitoring'
import type { ChartDataPoint, MetricLine } from '../monitoring'
import { StatCard } from '../ui/StatCard'

type MetricType = 'cpu' | 'memory' | 'network' | 'disk_io'

const METRIC_TABS: { id: MetricType; labelKey: string; icon: React.ElementType; color: string; gradient: string }[] = [
  { id: 'cpu', labelKey: 'admin:monitoring.metrics.cpu', icon: Cpu, color: 'blue', gradient: 'from-blue-500 to-blue-600' },
  { id: 'memory', labelKey: 'admin:monitoring.metrics.memory', icon: MemoryStick, color: 'emerald', gradient: 'from-emerald-500 to-emerald-600' },
  { id: 'network', labelKey: 'admin:monitoring.metrics.network', icon: Network, color: 'purple', gradient: 'from-purple-500 to-purple-600' },
  { id: 'disk_io', labelKey: 'admin:monitoring.metrics.diskIo', icon: HardDrive, color: 'amber', gradient: 'from-amber-500 to-amber-600' },
]

const CHART_CONFIG: Record<MetricType, { lines: MetricLine[]; yAxisLabel: string; yAxisDomain?: [number | 'auto', number | 'auto'] }> = {
  cpu: {
    lines: [{ dataKey: 'usage', name: 'CPU Usage', color: '#3b82f6' }],
    yAxisLabel: '%',
    yAxisDomain: [0, 100],
  },
  memory: {
    lines: [{ dataKey: 'percent', name: 'Memory', color: '#10b981' }],
    yAxisLabel: '%',
    yAxisDomain: [0, 100],
  },
  network: {
    lines: [
      { dataKey: 'download', name: 'Download', color: '#8b5cf6' },
      { dataKey: 'upload', name: 'Upload', color: '#06b6d4' },
    ],
    yAxisLabel: 'Mbps',
  },
  disk_io: {
    lines: [
      { dataKey: 'read', name: 'Read', color: '#f59e0b' },
      { dataKey: 'write', name: 'Write', color: '#ef4444' },
    ],
    yAxisLabel: 'MB/s',
  },
}

function computeStats(data: ChartDataPoint[], dataKeys: string[]): { min: number; max: number; avg: number } {
  if (data.length === 0) return { min: 0, max: 0, avg: 0 }
  let min = Infinity
  let max = -Infinity
  let sum = 0
  let count = 0
  for (const point of data) {
    for (const key of dataKeys) {
      const val = point[key]
      if (typeof val === 'number' && !isNaN(val)) {
        if (val < min) min = val
        if (val > max) max = val
        sum += val
        count++
      }
    }
  }
  if (count === 0) return { min: 0, max: 0, avg: 0 }
  return { min, max, avg: sum / count }
}

export default function MonitoringHistoryViewer() {
  const { t } = useTranslation(['admin', 'common'])
  const [activeMetric, setActiveMetric] = useState<MetricType>('cpu')
  const [timeRange, setTimeRange] = useState<TimeRange>('1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<string>('')
  const [sampleCount, setSampleCount] = useState<number>(0)

  // Data states
  const [cpuData, setCpuData] = useState<CpuHistoryResponse | null>(null)
  const [memoryData, setMemoryData] = useState<MemoryHistoryResponse | null>(null)
  const [networkData, setNetworkData] = useState<NetworkHistoryResponse | null>(null)
  const [diskIoData, setDiskIoData] = useState<DiskIoHistoryResponse | null>(null)

  // Disk selector
  const [selectedDisk, setSelectedDisk] = useState<string>('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      switch (activeMetric) {
        case 'cpu': {
          const data = await getCpuHistory(timeRange, 'database', 2000)
          setCpuData(data)
          setSource(data.source)
          setSampleCount(data.sample_count)
          break
        }
        case 'memory': {
          const data = await getMemoryHistory(timeRange, 'database', 2000)
          setMemoryData(data)
          setSource(data.source)
          setSampleCount(data.sample_count)
          break
        }
        case 'network': {
          const data = await getNetworkHistory(timeRange, 'database', 2000)
          setNetworkData(data)
          setSource(data.source)
          setSampleCount(data.sample_count)
          break
        }
        case 'disk_io': {
          const diskParam = selectedDisk || undefined
          const data = await getDiskIoHistory(timeRange, 'database', diskParam, 2000)
          setDiskIoData(data)
          setSource(data.source)
          setSampleCount(data.sample_count)
          // Set default disk if not selected
          if (!selectedDisk && data.available_disks.length > 0) {
            setSelectedDisk(data.available_disks[0])
          }
          break
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to load ${activeMetric} history`)
    } finally {
      setLoading(false)
    }
  }, [activeMetric, timeRange, selectedDisk])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Chart data mapping
  const chartData: ChartDataPoint[] = useMemo(() => {
    switch (activeMetric) {
      case 'cpu':
        return (cpuData?.samples || []).map(s => ({
          time: s.timestamp,
          usage: s.usage_percent,
        }))
      case 'memory':
        return (memoryData?.samples || []).map(s => ({
          time: s.timestamp,
          percent: s.percent,
        }))
      case 'network':
        return (networkData?.samples || []).map(s => ({
          time: s.timestamp,
          download: s.download_mbps,
          upload: s.upload_mbps,
        }))
      case 'disk_io': {
        const diskName = selectedDisk || Object.keys(diskIoData?.disks || {})[0] || ''
        const samples = diskIoData?.disks[diskName] || []
        return samples.map(s => ({
          time: s.timestamp,
          read: s.read_mbps,
          write: s.write_mbps,
        }))
      }
      default:
        return []
    }
  }, [activeMetric, cpuData, memoryData, networkData, diskIoData, selectedDisk])

  const config = CHART_CONFIG[activeMetric]
  const dataKeys = config.lines.map(l => l.dataKey)

  // Min/Max/Avg stats
  const stats = useMemo(() => computeStats(chartData, dataKeys), [chartData, dataKeys])

  const activeTab = METRIC_TABS.find(t => t.id === activeMetric)!
  const availableDisks = diskIoData?.available_disks || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('admin:monitoring.title')}</h3>
          <p className="text-xs text-slate-400 mt-1">
            {t('admin:monitoring.subtitle')}
            {sampleCount > 0 && (
              <span className="ml-2">
                ({t('admin:monitoring.samplesInfo', { count: sampleCount, formatted: sampleCount.toLocaleString(), source })})
              </span>
            )}
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 hover:text-white transition-colors text-sm border border-slate-600/50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {t('common:refresh')}
        </button>
      </div>

      {/* Metric Type Tabs — metric-colored */}
      <div className="flex flex-wrap gap-2">
        {METRIC_TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeMetric === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveMetric(tab.id)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                isActive
                  ? `bg-gradient-to-r ${tab.gradient} text-white shadow-lg shadow-${tab.color}-500/30`
                  : 'bg-slate-800/40 text-slate-300 border border-slate-700/50 hover:bg-slate-700/50 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t(tab.labelKey)}
            </button>
          )
        })}
      </div>

      {/* Time Range Selector + Disk Selector */}
      <div className="flex items-center gap-4 flex-wrap">
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />

        {activeMetric === 'disk_io' && availableDisks.length > 1 && (
          <select
            value={selectedDisk}
            onChange={(e) => setSelectedDisk(e.target.value)}
            className="rounded-lg px-3 py-1.5 text-sm bg-slate-800/60 text-slate-300 border border-slate-700/50 focus:border-amber-500/50 focus:outline-none"
          >
            {availableDisks.map((disk) => (
              <option key={disk} value={disk}>{disk}</option>
            ))}
          </select>
        )}
      </div>

      {/* Chart Container */}
      <div className="card !p-4">
        {error ? (
          <div className="h-[300px] flex flex-col items-center justify-center">
            <p className="text-red-400 mb-4">{error}</p>
            <button
              onClick={fetchData}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </button>
          </div>
        ) : (
          <MetricChart
            data={chartData}
            lines={config.lines}
            yAxisLabel={config.yAxisLabel}
            yAxisDomain={config.yAxisDomain}
            height={300}
            showArea
            loading={loading}
            timeRange={timeRange}
          />
        )}
      </div>

      {/* Min/Max/Avg Summary Strip */}
      {!loading && !error && chartData.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            label="Min"
            value={formatNumber(stats.min, 1)}
            unit={config.yAxisLabel}
            color={activeTab.color}
            icon={<TrendingDown className={`w-5 h-5 text-${activeTab.color}-400`} />}
          />
          <StatCard
            label="Avg"
            value={formatNumber(stats.avg, 1)}
            unit={config.yAxisLabel}
            color={activeTab.color}
            icon={<Activity className={`w-5 h-5 text-${activeTab.color}-400`} />}
          />
          <StatCard
            label="Max"
            value={formatNumber(stats.max, 1)}
            unit={config.yAxisLabel}
            color={activeTab.color}
            icon={<TrendingUp className={`w-5 h-5 text-${activeTab.color}-400`} />}
          />
        </div>
      )}

      {/* Info Note */}
      <div className="bg-slate-800/30 border border-slate-700/40 rounded-lg px-4 py-3">
        <p className="text-xs text-slate-400">
          {t('admin:monitoring.infoNote')}
        </p>
      </div>
    </div>
  )
}
