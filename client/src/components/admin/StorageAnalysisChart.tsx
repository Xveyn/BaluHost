import { useEffect, useState, useCallback } from 'react'
import { getDatabaseInfo } from '../../lib/api'
import type { DatabaseInfoResponse } from '../../lib/api'
import { RefreshCw, Database, HardDrive, Table } from 'lucide-react'
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

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

interface CustomTooltipProps {
  active?: boolean
  payload?: any[]
}

const CustomPieTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    const data = payload[0]
    return (
      <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-white text-sm font-medium">{data.name}</p>
        <p className="text-slate-300 text-xs">{formatBytes(data.value)}</p>
        <p className="text-slate-400 text-xs">{data.payload.percent?.toFixed(1)}%</p>
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
        <p className="text-slate-300 text-xs">Rows: {data.row_count.toLocaleString()}</p>
        <p className="text-slate-300 text-xs">Size: {formatBytes(data.estimated_size_bytes)}</p>
      </div>
    )
  }
  return null
}

export default function StorageAnalysisChart() {
  const [info, setInfo] = useState<DatabaseInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchInfo = useCallback(async () => {
    try {
      setError(null)
      const data = await getDatabaseInfo()
      setInfo(data)
    } catch (err: any) {
      setError(err?.message || 'Failed to load storage info')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchInfo()
  }, [fetchInfo])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
        <p className="text-slate-400">Loading storage analysis...</p>
      </div>
    )
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

  // Prepare data for pie chart (monitoring vs other tables)
  const monitoringSize = info.tables
    .filter(t => MONITORING_TABLES.includes(t.table_name))
    .reduce((sum, t) => sum + t.estimated_size_bytes, 0)

  const otherSize = info.tables
    .filter(t => !MONITORING_TABLES.includes(t.table_name))
    .reduce((sum, t) => sum + t.estimated_size_bytes, 0)

  const pieData = [
    { name: 'Monitoring Data', value: monitoringSize, percent: (monitoringSize / info.total_size_bytes) * 100 },
    { name: 'Application Data', value: otherSize, percent: (otherSize / info.total_size_bytes) * 100 },
  ].filter(d => d.value > 0)

  // Prepare data for bar chart (sorted by size)
  const barData = [...info.tables]
    .sort((a, b) => b.estimated_size_bytes - a.estimated_size_bytes)
    .slice(0, 10) // Top 10 tables

  // Calculate totals
  const totalRows = info.tables.reduce((sum, t) => sum + t.row_count, 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">Storage Analysis</h3>
          <p className="text-xs text-slate-400 mt-1">
            Database: {info.database_type} | Total Size: {formatBytes(info.total_size_bytes)}
          </p>
        </div>
        <button
          onClick={fetchInfo}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 hover:text-white transition-colors text-sm border border-slate-600/50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="w-4 h-4 text-blue-400" />
            <p className="text-xs text-slate-400">Total Size</p>
          </div>
          <p className="text-xl font-bold text-white">{formatBytes(info.total_size_bytes)}</p>
        </div>

        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Table className="w-4 h-4 text-emerald-400" />
            <p className="text-xs text-slate-400">Total Tables</p>
          </div>
          <p className="text-xl font-bold text-white">{info.tables.length}</p>
        </div>

        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-purple-400" />
            <p className="text-xs text-slate-400">Total Rows</p>
          </div>
          <p className="text-xl font-bold text-white">{totalRows.toLocaleString()}</p>
        </div>

        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-amber-400" />
            <p className="text-xs text-slate-400">Monitoring Data</p>
          </div>
          <p className="text-xl font-bold text-white">{formatBytes(monitoringSize)}</p>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart */}
        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
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

        {/* Bar Chart */}
        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
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
                  fill="#3b82f6"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-400 text-sm">
              No tables found
            </div>
          )}
        </div>
      </div>

      {/* Table List */}
      <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-white mb-4">All Tables</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50">
                <th className="text-left py-2 px-3 text-slate-400 font-medium">Table Name</th>
                <th className="text-right py-2 px-3 text-slate-400 font-medium">Rows</th>
                <th className="text-right py-2 px-3 text-slate-400 font-medium">Est. Size</th>
                <th className="text-right py-2 px-3 text-slate-400 font-medium">% of Total</th>
              </tr>
            </thead>
            <tbody>
              {info.tables
                .sort((a, b) => b.estimated_size_bytes - a.estimated_size_bytes)
                .map((table) => {
                  const isMonitoring = MONITORING_TABLES.includes(table.table_name)
                  const percent = info.total_size_bytes > 0
                    ? ((table.estimated_size_bytes / info.total_size_bytes) * 100).toFixed(1)
                    : '0'

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
                      <td className="py-2 px-3 text-right text-slate-400">
                        {percent}%
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
