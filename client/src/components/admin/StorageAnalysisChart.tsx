import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getDatabaseInfo } from '../../lib/api'
import type { DatabaseInfoResponse } from '../../lib/api'
import { RefreshCw, Database, HardDrive, Table, ArrowUp, ArrowDown, ArrowUpDown, BarChart3 } from 'lucide-react'
import { formatBytes, formatNumber } from '../../lib/formatters'
import { StatCard } from '../ui/StatCard'
import { ProgressBar } from '../ui/ProgressBar'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'

const COLORS = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#8b5cf6', // purple
  '#f59e0b', // amber
  '#ef4444', // red
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#84cc16', // lime
]

const MONITORING_TABLES = ['cpu_samples', 'memory_samples', 'network_samples', 'disk_io_samples', 'process_samples']

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; payload: { percent?: number; table_name?: string; row_count?: number; estimated_size_bytes?: number } }>
}

const CustomPieTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    const data = payload[0]
    return (
      <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-white text-sm font-medium">{data.name}</p>
        <p className="text-slate-300 text-xs">{formatBytes(data.value)}</p>
        <p className="text-slate-400 text-xs">{data.payload.percent != null ? formatNumber(data.payload.percent, 1) : ''}%</p>
      </div>
    )
  }
  return null
}

const CustomBarTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    return (
      <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-white text-sm font-medium">{data.table_name}</p>
        <p className="text-slate-300 text-xs">Rows: {data.row_count?.toLocaleString() ?? '—'}</p>
        <p className="text-slate-300 text-xs">Size: {formatBytes(data.estimated_size_bytes ?? 0)}</p>
      </div>
    )
  }
  return null
}

type SortField = 'table_name' | 'row_count' | 'estimated_size_bytes' | 'percent'
type SortDir = 'asc' | 'desc'

function StorageAnalysisSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div>
          <div className="h-6 w-48 rounded bg-slate-800 animate-pulse" />
          <div className="h-4 w-64 rounded bg-slate-800 animate-pulse mt-2" />
        </div>
        <div className="h-9 w-24 rounded-lg bg-slate-800 animate-pulse" />
      </div>
      {/* StatCards skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card !p-4 animate-pulse">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-slate-800" />
              <div className="h-3 w-20 rounded bg-slate-800" />
            </div>
            <div className="h-7 w-20 rounded bg-slate-800 mt-2" />
          </div>
        ))}
      </div>
      {/* Charts skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card !p-4 animate-pulse">
          <div className="h-4 w-32 rounded bg-slate-800 mb-4" />
          <div className="h-[250px] rounded bg-slate-800/50" />
        </div>
        <div className="card !p-4 animate-pulse">
          <div className="h-4 w-32 rounded bg-slate-800 mb-4" />
          <div className="h-[250px] rounded bg-slate-800/50" />
        </div>
      </div>
    </div>
  )
}

export default function StorageAnalysisChart() {
  const { t } = useTranslation(['admin', 'common'])
  const [info, setInfo] = useState<DatabaseInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortField, setSortField] = useState<SortField>('estimated_size_bytes')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const fetchInfo = useCallback(async () => {
    try {
      setError(null)
      const data = await getDatabaseInfo()
      setInfo(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load storage info')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchInfo()
  }, [fetchInfo])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 text-slate-500" />
    return sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 text-blue-400" />
      : <ArrowDown className="w-3 h-3 text-blue-400" />
  }

  if (loading) {
    return <StorageAnalysisSkeleton />
  }

  if (error) {
    return (
      <div className="bg-gradient-to-r from-red-500/10 to-red-600/5 border border-red-500/30 rounded-xl px-5 py-4 backdrop-blur-sm">
        <p className="text-red-400 text-sm font-medium">{error}</p>
        <button
          onClick={fetchInfo}
          className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors text-sm"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    )
  }

  if (!info) return null

  // Prepare data for pie chart — top 8 tables individually + "Other"
  const sortedBySize = [...info.tables].sort((a, b) => b.estimated_size_bytes - a.estimated_size_bytes)
  const top8 = sortedBySize.slice(0, 8)
  const otherSize = sortedBySize.slice(8).reduce((sum, t) => sum + t.estimated_size_bytes, 0)

  const pieData = [
    ...top8.map(t => ({
      name: t.table_name,
      value: t.estimated_size_bytes,
      percent: info.total_size_bytes > 0 ? (t.estimated_size_bytes / info.total_size_bytes) * 100 : 0,
    })),
    ...(otherSize > 0 ? [{
      name: 'Other',
      value: otherSize,
      percent: info.total_size_bytes > 0 ? (otherSize / info.total_size_bytes) * 100 : 0,
    }] : []),
  ].filter(d => d.value > 0)

  // Prepare data for bar chart (sorted by size, colored)
  const barData = sortedBySize.slice(0, 10).map((t, index) => ({
    ...t,
    fill: MONITORING_TABLES.includes(t.table_name) ? '#3b82f6' : COLORS[index % COLORS.length],
  }))

  // Calculate totals
  const totalRows = info.tables.reduce((sum, t) => sum + t.row_count, 0)
  const monitoringSize = info.tables
    .filter(t => MONITORING_TABLES.includes(t.table_name))
    .reduce((sum, t) => sum + t.estimated_size_bytes, 0)

  // Sorted table data
  const sortedTables = [...info.tables].sort((a, b) => {
    const aPercent = info.total_size_bytes > 0 ? (a.estimated_size_bytes / info.total_size_bytes) * 100 : 0
    const bPercent = info.total_size_bytes > 0 ? (b.estimated_size_bytes / info.total_size_bytes) * 100 : 0
    let cmp = 0
    switch (sortField) {
      case 'table_name': cmp = a.table_name.localeCompare(b.table_name); break
      case 'row_count': cmp = a.row_count - b.row_count; break
      case 'estimated_size_bytes': cmp = a.estimated_size_bytes - b.estimated_size_bytes; break
      case 'percent': cmp = aPercent - bPercent; break
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('admin:storageAnalysis.title')}</h3>
          <p className="text-xs text-slate-400 mt-1">
            {t('admin:storageAnalysis.subtitle', { type: info.database_type, size: formatBytes(info.total_size_bytes) })}
          </p>
        </div>
        <button
          onClick={fetchInfo}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 hover:text-white transition-colors text-sm border border-slate-600/50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {t('common:refresh')}
        </button>
      </div>

      {/* Summary StatCards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label={t('admin:storageAnalysis.summary.totalSize')}
          value={formatBytes(info.total_size_bytes)}
          color="blue"
          icon={<HardDrive className="w-5 h-5 text-blue-400" />}
        />
        <StatCard
          label={t('admin:storageAnalysis.summary.totalTables')}
          value={info.tables.length}
          color="emerald"
          icon={<Table className="w-5 h-5 text-emerald-400" />}
        />
        <StatCard
          label={t('admin:storageAnalysis.summary.totalRows')}
          value={totalRows.toLocaleString()}
          color="purple"
          icon={<Database className="w-5 h-5 text-purple-400" />}
        />
        <StatCard
          label={t('admin:storageAnalysis.summary.monitoringData')}
          value={formatBytes(monitoringSize)}
          color="amber"
          icon={<BarChart3 className="w-5 h-5 text-amber-400" />}
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart — Top 8 + Other */}
        <div className="card !p-4">
          <h4 className="text-sm font-semibold text-white mb-4">Data Distribution</h4>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomPieTooltip />} />
                <Legend
                  formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-400 text-sm">
              No data available
            </div>
          )}
        </div>

        {/* Bar Chart — colored bars */}
        <div className="card !p-4">
          <h4 className="text-sm font-semibold text-white mb-4">Top Tables by Size</h4>
          {barData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart
                data={barData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  type="number"
                  tickFormatter={(value) => formatBytes(value)}
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                />
                <YAxis
                  type="category"
                  dataKey="table_name"
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  width={80}
                />
                <Tooltip content={<CustomBarTooltip />} />
                <Bar
                  dataKey="estimated_size_bytes"
                  radius={[0, 4, 4, 0]}
                >
                  {barData.map((entry, index) => (
                    <Cell key={`bar-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-400 text-sm">
              No tables found
            </div>
          )}
        </div>
      </div>

      {/* Sortable Table List */}
      <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-white mb-4">All Tables</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50">
                <th
                  className="text-left py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 transition-colors select-none"
                  onClick={() => handleSort('table_name')}
                >
                  <span className="inline-flex items-center gap-1">Table Name <SortIcon field="table_name" /></span>
                </th>
                <th
                  className="text-right py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 transition-colors select-none"
                  onClick={() => handleSort('row_count')}
                >
                  <span className="inline-flex items-center gap-1 justify-end">Rows <SortIcon field="row_count" /></span>
                </th>
                <th
                  className="text-right py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 transition-colors select-none"
                  onClick={() => handleSort('estimated_size_bytes')}
                >
                  <span className="inline-flex items-center gap-1 justify-end">Est. Size <SortIcon field="estimated_size_bytes" /></span>
                </th>
                <th
                  className="text-right py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 transition-colors select-none w-44"
                  onClick={() => handleSort('percent')}
                >
                  <span className="inline-flex items-center gap-1 justify-end">% of Total <SortIcon field="percent" /></span>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedTables.map((table) => {
                const isMonitoring = MONITORING_TABLES.includes(table.table_name)
                const percentVal = info.total_size_bytes > 0
                  ? (table.estimated_size_bytes / info.total_size_bytes) * 100
                  : 0

                return (
                  <tr
                    key={table.table_name}
                    className={`border-b border-slate-700/30 hover:bg-slate-700/20 transition-colors ${
                      isMonitoring ? 'bg-blue-500/5' : ''
                    }`}
                  >
                    <td className="py-2 px-3">
                      <span className="text-white">{table.table_name}</span>
                      {isMonitoring && (
                        <span className="ml-2 text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                          Monitoring
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-slate-300 font-mono">
                      {table.row_count.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-right text-slate-300 font-mono">
                      {formatBytes(table.estimated_size_bytes)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <ProgressBar progress={percentVal} size="sm" className="w-16" />
                        <span className="text-slate-400 font-mono text-xs w-12 text-right">
                          {formatNumber(percentVal, 1)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
