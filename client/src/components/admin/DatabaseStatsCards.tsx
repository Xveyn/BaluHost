import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getDatabaseStats } from '../../api/monitoring'
import type { DatabaseStatsResponse, MetricDatabaseStats } from '../../api/monitoring'
import { Database, Cpu, MemoryStick, Network, HardDrive, Activity, RefreshCw } from 'lucide-react'

const METRIC_CONFIG: Record<string, { labelKey: string; icon: React.ElementType; color: string }> = {
  cpu: { labelKey: 'admin:databaseStats.metrics.cpu', icon: Cpu, color: 'blue' },
  memory: { labelKey: 'admin:databaseStats.metrics.memory', icon: MemoryStick, color: 'emerald' },
  network: { labelKey: 'admin:databaseStats.metrics.network', icon: Network, color: 'purple' },
  disk_io: { labelKey: 'admin:databaseStats.metrics.diskIo', icon: HardDrive, color: 'amber' },
  process: { labelKey: 'admin:databaseStats.metrics.process', icon: Activity, color: 'rose' },
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface MetricCardProps {
  metricType: string
  stats: MetricDatabaseStats
  t: (key: string, options?: Record<string, unknown>) => string
}

function MetricCard({ metricType, stats, t }: MetricCardProps) {
  const config = METRIC_CONFIG[metricType] || { labelKey: metricType, icon: Database, color: 'slate' }
  const Icon = config.icon
  const colorClasses: Record<string, { border: string; bg: string; text: string; glow: string }> = {
    blue: { border: 'hover:border-blue-500/50', bg: 'from-blue-500/20 to-blue-600/10', text: 'text-blue-400', glow: 'hover:shadow-blue-500/10' },
    emerald: { border: 'hover:border-emerald-500/50', bg: 'from-emerald-500/20 to-emerald-600/10', text: 'text-emerald-400', glow: 'hover:shadow-emerald-500/10' },
    purple: { border: 'hover:border-purple-500/50', bg: 'from-purple-500/20 to-purple-600/10', text: 'text-purple-400', glow: 'hover:shadow-purple-500/10' },
    amber: { border: 'hover:border-amber-500/50', bg: 'from-amber-500/20 to-amber-600/10', text: 'text-amber-400', glow: 'hover:shadow-amber-500/10' },
    rose: { border: 'hover:border-rose-500/50', bg: 'from-rose-500/20 to-rose-600/10', text: 'text-rose-400', glow: 'hover:shadow-rose-500/10' },
    slate: { border: 'hover:border-slate-500/50', bg: 'from-slate-500/20 to-slate-600/10', text: 'text-slate-400', glow: 'hover:shadow-slate-500/10' },
  }
  const colors = colorClasses[config.color] || colorClasses.slate

  return (
    <div className={`group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 ${colors.border} transition-all duration-300 hover:shadow-2xl ${colors.glow} overflow-hidden`}>
      <div className={`absolute inset-0 bg-gradient-to-br ${colors.bg.replace('from-', 'from-').replace('/20', '/5')} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />

      <div className="relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className={`w-8 h-8 bg-gradient-to-br ${colors.bg} rounded-lg flex items-center justify-center`}>
              <Icon className={`w-4 h-4 ${colors.text}`} />
            </div>
            <h3 className="text-sm font-semibold text-white">{t(config.labelKey)}</h3>
          </div>
          <span className={`text-xs font-medium px-2 py-1 rounded-lg bg-slate-800/60 ${colors.text}`}>
            {t('admin:databaseStats.fields.retention', { hours: stats.retention_hours })}
          </span>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-slate-400 mb-1">{t('admin:databaseStats.fields.samples')}</p>
            <p className="text-lg font-bold text-white">{stats.count.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 mb-1">{t('admin:databaseStats.fields.size')}</p>
            <p className="text-lg font-bold text-white">{formatBytes(stats.estimated_size_bytes)}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs text-slate-400 mb-1">{t('admin:databaseStats.fields.lastCleanup')}</p>
            <p className="text-sm text-slate-300">{formatDate(stats.last_cleanup)}</p>
          </div>
          {stats.total_cleaned > 0 && (
            <div className="col-span-2">
              <p className="text-xs text-slate-400 mb-1">{t('admin:databaseStats.fields.totalCleaned')}</p>
              <p className="text-sm text-slate-300">{stats.total_cleaned.toLocaleString()}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface DatabaseStatsCardsProps {
  autoRefresh?: boolean
  refreshInterval?: number
}

export default function DatabaseStatsCards({ autoRefresh = true, refreshInterval = 30000 }: DatabaseStatsCardsProps) {
  const { t } = useTranslation(['admin', 'common'])
  const [stats, setStats] = useState<DatabaseStatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchStats = useCallback(async () => {
    try {
      setError(null)
      const data = await getDatabaseStats()
      setStats(data)
      setLastUpdate(new Date())
    } catch (err: any) {
      setError(err?.message || 'Failed to load database stats')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStats()

    if (autoRefresh) {
      const interval = setInterval(fetchStats, refreshInterval)
      return () => clearInterval(interval)
    }
  }, [fetchStats, autoRefresh, refreshInterval])

  if (loading && !stats) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
        <p className="text-slate-400">{t('admin:databaseStats.loading')}</p>
      </div>
    )
  }

  if (error && !stats) {
    return (
      <div className="bg-gradient-to-r from-red-500/10 to-red-600/5 border border-red-500/30 rounded-xl px-5 py-4 backdrop-blur-sm">
        <p className="text-red-400 text-sm font-medium">{error}</p>
        <button
          onClick={fetchStats}
          className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors text-sm"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    )
  }

  if (!stats) return null

  const metricTypes = Object.keys(stats.metrics)

  return (
    <div className="space-y-6">
      {/* Header with refresh info */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('admin:databaseStats.title')}</h3>
          {lastUpdate && (
            <p className="text-xs text-slate-400 mt-1">
              {t('admin:databaseStats.lastUpdated', { time: lastUpdate.toLocaleTimeString('de-DE') })}
              {autoRefresh && ` ${t('admin:databaseStats.autoRefresh', { seconds: refreshInterval / 1000 })}`}
            </p>
          )}
        </div>
        <button
          onClick={fetchStats}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 hover:text-white transition-colors text-sm border border-slate-600/50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {t('common:refresh')}
        </button>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {metricTypes.map((metricType) => (
          <MetricCard key={metricType} metricType={metricType} stats={stats.metrics[metricType]} t={t} />
        ))}
      </div>

      {/* Summary Card */}
      <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-xl flex items-center justify-center">
              <Database className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">{t('admin:databaseStats.summary.totalSamples')}</p>
              <p className="text-xl font-bold text-white">{stats.total_samples.toLocaleString()}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 rounded-xl flex items-center justify-center">
              <HardDrive className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">{t('admin:databaseStats.summary.totalSize')}</p>
              <p className="text-xl font-bold text-white">{formatBytes(stats.total_size_bytes)}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-xl flex items-center justify-center">
              <Activity className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">{t('admin:databaseStats.summary.metricTypes')}</p>
              <p className="text-xl font-bold text-white">{metricTypes.length}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
