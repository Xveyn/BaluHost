import { useEffect, useState, useCallback } from 'react'
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
import { formatTimeForRange, parseUtcTimestamp } from '../../lib/dateUtils'
import { formatNumber } from '../../lib/formatters'
import { RefreshCw, Cpu, MemoryStick, Network, HardDrive, Clock } from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

type MetricType = 'cpu' | 'memory' | 'network' | 'disk_io'

const METRIC_TABS: { id: MetricType; labelKey: string; icon: React.ElementType; color: string }[] = [
  { id: 'cpu', labelKey: 'admin:monitoring.metrics.cpu', icon: Cpu, color: 'blue' },
  { id: 'memory', labelKey: 'admin:monitoring.metrics.memory', icon: MemoryStick, color: 'emerald' },
  { id: 'network', labelKey: 'admin:monitoring.metrics.network', icon: Network, color: 'purple' },
  { id: 'disk_io', labelKey: 'admin:monitoring.metrics.diskIo', icon: HardDrive, color: 'amber' },
]

const TIME_RANGES: { value: TimeRange; labelKey: string }[] = [
  { value: '10m', labelKey: 'admin:monitoring.timeRanges.10m' },
  { value: '1h', labelKey: 'admin:monitoring.timeRanges.1h' },
  { value: '24h', labelKey: 'admin:monitoring.timeRanges.24h' },
  { value: '7d', labelKey: 'admin:monitoring.timeRanges.7d' },
]

// formatDate and formatDateFull replaced by shared formatTimeForRange()

interface CustomTooltipProps {
  active?: boolean
  payload?: any[]
  label?: string
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (active && payload && payload.length && label) {
    const fullDate = parseUtcTimestamp(label).toLocaleString();
    return (
      <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-slate-400 text-xs mb-1">{fullDate}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ? formatNumber(entry.value, 2) : entry.value}
            {entry.unit || ''}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function MonitoringHistoryViewer() {
  const { t, i18n } = useTranslation(['admin', 'common'])
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

  const tickFormatter = (dateStr: string) => formatTimeForRange(dateStr, timeRange, i18n.language)
  const minTickGap = timeRange === '7d' ? 70 : 40

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
          const data = await getDiskIoHistory(timeRange, 'database', undefined, 2000)
          setDiskIoData(data)
          setSource(data.source)
          setSampleCount(data.sample_count)
          break
        }
      }
    } catch (err: any) {
      setError(err?.message || `Failed to load ${activeMetric} history`)
    } finally {
      setLoading(false)
    }
  }, [activeMetric, timeRange])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const renderCpuChart = () => {
    if (!cpuData || cpuData.samples.length === 0) {
      return (
        <div className="h-[300px] flex items-center justify-center text-slate-400">
          {t('admin:monitoring.noDataAvailable', { metric: t('admin:monitoring.metrics.cpu') })}
        </div>
      )
    }

    const chartData = cpuData.samples.map(s => ({
      timestamp: s.timestamp,
      usage: s.usage_percent,
      frequency: s.frequency_mhz ? s.frequency_mhz / 1000 : null,
    }))

    return (
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={tickFormatter}
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            interval="preserveStartEnd"
            minTickGap={minTickGap}
          />
          <YAxis
            domain={[0, 100]}
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Area
            type="monotone"
            dataKey="usage"
            name={t('admin:monitoring.charts.cpuUsage')}
            stroke="#3b82f6"
            fill="url(#cpuGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  const renderMemoryChart = () => {
    if (!memoryData || memoryData.samples.length === 0) {
      return (
        <div className="h-[300px] flex items-center justify-center text-slate-400">
          {t('admin:monitoring.noDataAvailable', { metric: t('admin:monitoring.metrics.memory') })}
        </div>
      )
    }

    const chartData = memoryData.samples.map(s => ({
      timestamp: s.timestamp,
      usedGB: s.used_bytes / (1024 * 1024 * 1024),
      percent: s.percent,
    }))

    return (
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="memoryGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={tickFormatter}
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            interval="preserveStartEnd"
            minTickGap={minTickGap}
          />
          <YAxis
            domain={[0, 100]}
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Area
            type="monotone"
            dataKey="percent"
            name={t('admin:monitoring.charts.memoryUsage')}
            stroke="#10b981"
            fill="url(#memoryGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  const renderNetworkChart = () => {
    if (!networkData || networkData.samples.length === 0) {
      return (
        <div className="h-[300px] flex items-center justify-center text-slate-400">
          {t('admin:monitoring.noDataAvailable', { metric: t('admin:monitoring.metrics.network') })}
        </div>
      )
    }

    const chartData = networkData.samples.map(s => ({
      timestamp: s.timestamp,
      download: s.download_mbps,
      upload: s.upload_mbps,
    }))

    return (
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="downloadGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="uploadGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={tickFormatter}
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            interval="preserveStartEnd"
            minTickGap={minTickGap}
          />
          <YAxis
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            tickFormatter={(v) => `${v} Mbps`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Area
            type="monotone"
            dataKey="download"
            name={t('admin:monitoring.charts.download')}
            stroke="#8b5cf6"
            fill="url(#downloadGradient)"
            strokeWidth={2}
          />
          <Area
            type="monotone"
            dataKey="upload"
            name={t('admin:monitoring.charts.upload')}
            stroke="#06b6d4"
            fill="url(#uploadGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  const renderDiskIoChart = () => {
    if (!diskIoData || Object.keys(diskIoData.disks).length === 0) {
      return (
        <div className="h-[300px] flex items-center justify-center text-slate-400">
          {t('admin:monitoring.noDataAvailable', { metric: t('admin:monitoring.metrics.diskIo') })}
        </div>
      )
    }

    // Aggregate all disks into a single chart (sum of read/write)
    const diskNames = Object.keys(diskIoData.disks)
    const firstDisk = diskNames[0]
    const samples = diskIoData.disks[firstDisk] || []

    if (samples.length === 0) {
      return (
        <div className="h-[300px] flex items-center justify-center text-slate-400">
          {t('admin:monitoring.noSamplesAvailable', { metric: t('admin:monitoring.metrics.diskIo') })}
        </div>
      )
    }

    const chartData = samples.map(s => ({
      timestamp: s.timestamp,
      read: s.read_mbps,
      write: s.write_mbps,
    }))

    return (
      <div>
        <p className="text-xs text-slate-400 mb-2">
          {t('admin:monitoring.showingDisk', { disk: firstDisk, count: diskNames.length })}
        </p>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="readGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="writeGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={tickFormatter}
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              interval="preserveStartEnd"
              minTickGap={minTickGap}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              tickFormatter={(v) => `${v} MB/s`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Area
              type="monotone"
              dataKey="read"
              name={t('admin:monitoring.charts.read')}
              stroke="#f59e0b"
              fill="url(#readGradient)"
              strokeWidth={2}
            />
            <Area
              type="monotone"
              dataKey="write"
              name={t('admin:monitoring.charts.write')}
              stroke="#ef4444"
              fill="url(#writeGradient)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const renderChart = () => {
    if (loading) {
      return (
        <div className="h-[300px] flex flex-col items-center justify-center">
          <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
          <p className="text-slate-400">{t('admin:monitoring.loadingHistory')}</p>
        </div>
      )
    }

    if (error) {
      return (
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
      )
    }

    switch (activeMetric) {
      case 'cpu':
        return renderCpuChart()
      case 'memory':
        return renderMemoryChart()
      case 'network':
        return renderNetworkChart()
      case 'disk_io':
        return renderDiskIoChart()
      default:
        return null
    }
  }

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

      {/* Metric Type Tabs */}
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
                  ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30'
                  : 'bg-slate-800/40 text-slate-300 border border-slate-700/50 hover:bg-slate-700/50 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t(tab.labelKey)}
            </button>
          )
        })}
      </div>

      {/* Time Range Selector */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-slate-400">
          <Clock className="w-4 h-4" />
          <span className="text-sm">{t('admin:monitoring.timeRange')}:</span>
        </div>
        <div className="flex gap-2">
          {TIME_RANGES.map((range) => (
            <button
              key={range.value}
              onClick={() => setTimeRange(range.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                timeRange === range.value
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                  : 'bg-slate-800/40 text-slate-400 border border-slate-700/50 hover:bg-slate-700/50 hover:text-slate-300'
              }`}
            >
              {t(range.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Container */}
      <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
        {renderChart()}
      </div>

      {/* Info Note */}
      <div className="bg-slate-800/30 border border-slate-700/40 rounded-lg px-4 py-3">
        <p className="text-xs text-slate-400">
          {t('admin:monitoring.infoNote')}
        </p>
      </div>
    </div>
  )
}
