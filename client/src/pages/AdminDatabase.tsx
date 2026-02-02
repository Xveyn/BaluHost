import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import useAdminDb from '../hooks/useAdminDb'
import AdminDataTable from '../components/AdminDataTable'
import { rowsToCsv } from '../lib/csv'
import { Database, Table, Download, ChevronLeft, ChevronRight, RefreshCw, BarChart3, History, Wrench } from 'lucide-react'
import DatabaseStatsCards from '../components/admin/DatabaseStatsCards'
import MaintenanceTools from '../components/admin/MaintenanceTools'
import StorageAnalysisChart from '../components/admin/StorageAnalysisChart'
import MonitoringHistoryViewer from '../components/admin/MonitoringHistoryViewer'

type TabType = 'tables' | 'stats' | 'storage' | 'history' | 'maintenance'

export default function AdminDatabase() {
  const { t } = useTranslation('admin');
  const [activeTab, setActiveTab] = useState<TabType>('tables')
  const [tables, setTables] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [pageSize] = useState<number>(50)

  const tabs = [
    { id: 'tables' as TabType, label: t('database.tabs.tables'), icon: Table },
    { id: 'stats' as TabType, label: t('database.tabs.stats'), icon: BarChart3 },
    { id: 'storage' as TabType, label: t('database.tabs.storage'), icon: Database },
    { id: 'history' as TabType, label: t('database.tabs.history'), icon: History },
    { id: 'maintenance' as TabType, label: t('database.tabs.maintenance'), icon: Wrench },
  ];

  const { fetchTables, fetchSchema, fetchRows } = useAdminDb()
  const [schema, setSchema] = useState<any | null>(null)
  const [rows, setRows] = useState<any[]>([])
  const [ownerMap, setOwnerMap] = useState<Record<string,string>>({})
  const [ownerLoadInfo, setOwnerLoadInfo] = useState<{status: 'idle'|'loading'|'loaded'|'failed', page_size?: number, count?: number, keys?: string[], error?: string}>({status: 'idle'})
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const totalPages = total ? Math.ceil((total ?? 0) / pageSize) : null
  useEffect(() => {
    let mounted = true
    setError(null)
    fetchTables()
      .then((t) => { if (mounted) setTables(t) })
      .catch((e) => { console.error('Failed to load admin tables', e); if (mounted) setError('Failed to load tables') })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!selected) return
    let mounted = true
    setLoading(true)
    setError(null)
    Promise.all([fetchSchema(selected), fetchRows(selected, page, pageSize)])
      .then(([s, r]) => {
        if (!mounted) return
        console.log('Fetched rows response:', r)
        console.log('Total from response:', r.total)
        setSchema(s)
        setRows(r.rows)
        setTotal(r.total ?? null)
      })
      .catch((e) => {
        console.error('Failed to load table data', e)
        if (mounted) setError('Fehler beim Laden der Tabellendaten')
      })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [selected, page, pageSize])

  // Manual owner mapping loader to avoid accidental heavy DB queries.
  // Call `loadOwners()` (e.g. from UI) to populate `ownerMap` on demand.
  const loadOwners = async () => {
    if (!tables.includes('users')) {
      setOwnerLoadInfo({ status: 'failed', error: 'users table not available' })
      return
    }
    setOwnerLoadInfo({ status: 'loading' })
    let mounted = true
    try {
      const sizes = [2000, 1000, 500, 200, 100, 50]
      let successful = false
      for (const sz of sizes) {
        try {
          const res = await fetchRows('users', 1, sz)
          if (!mounted) return
          const map: Record<string,string> = {}
          for (const u of res.rows || []) {
            const id = u.id ?? u.ID ?? u.user_id ?? u.userId
            const name = u.username ?? u.user_name ?? u.name ?? u.display_name ?? u.displayName ?? ''
            if (id !== undefined) map[String(id)] = name
          }
          setOwnerMap(map)
          setOwnerLoadInfo({ status: 'loaded', page_size: sz, count: (res.rows || []).length, keys: Object.keys(map).slice(0,20) })
          successful = true
          break
        } catch (err: any) {
          const status = err?.response?.status
          if (status && status !== 422) {
            setOwnerLoadInfo({ status: 'failed', error: `HTTP ${status}` })
            break
          }
          setOwnerLoadInfo({ status: 'loading', page_size: sz })
        }
      }
      if (!successful) setOwnerLoadInfo({ status: 'failed', error: 'no successful response' })
    } catch (e) {
      setOwnerLoadInfo({ status: 'failed', error: String(e) })
    }
  }

  // Render Tables Tab Content
  const renderTablesContent = () => (
    <>
      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-6 lg:grid-cols-3 mb-6 sm:mb-8">
        {/* Total Tables Card */}
        <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl p-4 sm:p-6 hover:border-blue-500/50 transition-all duration-300 hover:shadow-2xl hover:shadow-blue-500/10 overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
          <div className="relative flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-xs sm:text-sm font-medium mb-1 sm:mb-2">Total Tables</p>
              <p className="text-2xl sm:text-4xl font-bold bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                {tables.length}
              </p>
            </div>
            <div className="w-10 h-10 sm:w-14 sm:h-14 bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-lg sm:rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
              <Database className="w-5 h-5 sm:w-7 sm:h-7 text-blue-400" />
            </div>
          </div>
        </div>

        {/* Selected Table Card */}
        <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl p-4 sm:p-6 hover:border-emerald-500/50 transition-all duration-300 hover:shadow-2xl hover:shadow-emerald-500/10 overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
          <div className="relative flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <p className="text-slate-400 text-xs sm:text-sm font-medium mb-1 sm:mb-2">Selected Table</p>
              <p className="text-lg sm:text-2xl font-bold bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent truncate">
                {selected || 'None'}
              </p>
            </div>
            <div className="w-10 h-10 sm:w-14 sm:h-14 bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 rounded-lg sm:rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform duration-300 flex-shrink-0 ml-2 sm:ml-4">
              <Table className="w-5 h-5 sm:w-7 sm:h-7 text-emerald-400" />
            </div>
          </div>
        </div>

        {/* Total Rows Card */}
        <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl p-4 sm:p-6 hover:border-purple-500/50 transition-all duration-300 hover:shadow-2xl hover:shadow-purple-500/10 overflow-hidden col-span-2 lg:col-span-1">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
          <div className="relative flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-xs sm:text-sm font-medium mb-1 sm:mb-2">Total Rows</p>
              <p className="text-2xl sm:text-4xl font-bold bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                {!selected ? '—' : total !== null ? total.toLocaleString() : '0'}
              </p>
            </div>
            <div className="w-10 h-10 sm:w-14 sm:h-14 bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-lg sm:rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
              <RefreshCw className="w-5 h-5 sm:w-7 sm:h-7 text-purple-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Table Selector Pills */}
      <div className="mb-4 sm:mb-6">
        <div className="flex flex-wrap gap-2 sm:gap-3 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 pb-2 sm:pb-0">
          {tables.map((t) => (
            <button
              key={t}
              onClick={() => { setSelected(t); setPage(1) }}
              className={`relative px-3 sm:px-5 py-2 sm:py-2.5 rounded-lg sm:rounded-xl text-xs sm:text-sm font-semibold transition-all duration-300 touch-manipulation active:scale-95 whitespace-nowrap min-h-[44px] ${
                selected === t
                  ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30 scale-105'
                  : 'bg-slate-800/40 text-slate-300 border border-slate-700/50 hover:bg-slate-700/50 hover:border-slate-600/50 hover:text-white'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Card */}
      <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />

        {/* Card Header */}
        <div className="relative px-4 sm:px-6 py-4 sm:py-5 border-b border-slate-700/50 bg-slate-800/30">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
            <div>
              <h2 className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                {selected ?? 'Database View'}
              </h2>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">Select a table to view schema and rows</p>
            </div>

            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              {/* Pagination */}
              {selected && (
                <div className="flex items-center gap-1 sm:gap-2">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    className={`p-2 sm:p-2.5 rounded-lg sm:rounded-xl border transition-all duration-200 touch-manipulation active:scale-95 min-h-[44px] min-w-[44px] flex items-center justify-center ${
                      page <= 1
                        ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                        : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:border-blue-500/50 hover:text-white'
                    }`}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="w-5 h-5" />
                  </button>
                  <div className="text-xs sm:text-sm text-slate-300 font-medium min-w-[70px] sm:min-w-[100px] text-center px-2 sm:px-3">
                    {page}{totalPages ? ` / ${totalPages}` : ''}
                  </div>
                  <button
                    onClick={() => setPage(page + 1)}
                    className={`p-2 sm:p-2.5 rounded-lg sm:rounded-xl border transition-all duration-200 touch-manipulation active:scale-95 min-h-[44px] min-w-[44px] flex items-center justify-center ${
                      totalPages !== null && page >= (totalPages ?? 1)
                        ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                        : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:border-blue-500/50 hover:text-white'
                    }`}
                    disabled={totalPages !== null && page >= (totalPages ?? 1)}
                  >
                    <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              )}

              {/* Export Button */}
              <button
                disabled={!selected || rows.length === 0}
                className={`inline-flex items-center gap-2 px-3 sm:px-5 py-2 sm:py-2.5 rounded-lg sm:rounded-xl text-xs sm:text-sm font-semibold transition-all duration-200 touch-manipulation active:scale-95 min-h-[44px] ${
                  selected && rows.length
                    ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white hover:from-blue-600 hover:to-blue-700 shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 hover:scale-105'
                    : 'bg-slate-700/40 text-slate-500 cursor-not-allowed border border-slate-700/50'
                }`}
                onClick={() => {
                  if (!selected || rows.length === 0) return
                  const cols = schema?.columns?.map((c: any) => c.name) ?? []
                  const csv = rowsToCsv(rows, cols)
                  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `${selected}.csv`
                  document.body.appendChild(a)
                  a.click()
                  a.remove()
                  URL.revokeObjectURL(url)
                }}
              >
                <Download className="w-4 h-4" />
                <span className="hidden sm:inline">Export</span> CSV
              </button>
            </div>
          </div>
        </div>

        {/* Card Body */}
        <div className="relative p-4 sm:p-6">
          {!selected && (
            <div className="text-center py-20">
              <div className="relative inline-block">
                <div className="absolute inset-0 bg-blue-500/20 blur-3xl rounded-full" />
                <Database className="relative w-20 h-20 text-slate-600 mx-auto mb-6" />
              </div>
              <p className="text-slate-400 text-xl font-medium">Select a table to view its data</p>
              <p className="text-slate-500 text-sm mt-2">Choose from the available tables above</p>
            </div>
          )}

          {selected && (
            <>
              {error && (
                <div className="bg-gradient-to-r from-red-500/10 to-red-600/5 border border-red-500/30 rounded-xl px-5 py-4 mb-6 backdrop-blur-sm">
                  <p className="text-red-400 text-sm font-medium">{error}</p>
                </div>
              )}

              {/* Schema Section */}
              <div className="mb-6">
                <h3 className="text-sm font-bold text-slate-300 mb-4 flex items-center gap-2 uppercase tracking-wider">
                  <Database className="w-4 h-4 text-blue-400" />
                  Table Schema
                </h3>
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-5 overflow-auto max-h-[220px] hover:border-slate-600/50 transition-colors duration-200">
                  <pre className="text-xs text-slate-300 font-mono leading-relaxed">
                    {schema ? JSON.stringify(schema, null, 2) : (
                      <span className="text-slate-500 italic">Loading schema...</span>
                    )}
                  </pre>
                </div>
              </div>

              {/* Owner Mapping Section */}
              <details className="mb-6 group bg-slate-900/40 border border-slate-700/50 rounded-xl overflow-hidden hover:border-slate-600/50 transition-colors duration-200">
                <summary className="cursor-pointer px-5 py-4 text-sm font-bold text-slate-300 hover:text-white transition-colors uppercase tracking-wider flex items-center gap-2">
                  <svg className="w-4 h-4 text-purple-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  Owner Mapping Info
                </summary>
                <div className="px-5 pb-5 pt-2 bg-slate-900/20">
                  <div className="space-y-3 text-xs">
                    <div className="flex items-center gap-3">
                      <span className="text-slate-400 font-medium min-w-[100px]">Status:</span>
                      <span className={`px-3 py-1 rounded-lg font-semibold ${
                        ownerLoadInfo.status === 'loaded' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                        ownerLoadInfo.status === 'loading' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' :
                        ownerLoadInfo.status === 'failed' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                        'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                      }`}>
                        {ownerLoadInfo.status.toUpperCase()}
                      </span>
                    </div>
                    {ownerLoadInfo.page_size && (
                      <div className="flex items-center gap-3">
                        <span className="text-slate-400 font-medium min-w-[100px]">Page size tried:</span>
                        <span className="font-mono text-slate-300 bg-slate-800/50 px-2 py-1 rounded">{ownerLoadInfo.page_size}</span>
                      </div>
                    )}
                    {ownerLoadInfo.count !== undefined && (
                      <div className="flex items-center gap-3">
                        <span className="text-slate-400 font-medium min-w-[100px]">Loaded rows:</span>
                        <span className="font-mono text-slate-300 bg-slate-800/50 px-2 py-1 rounded">{ownerLoadInfo.count}</span>
                      </div>
                    )}
                    {ownerLoadInfo.keys && ownerLoadInfo.keys.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-slate-700/50">
                        <span className="text-slate-400 font-medium block mb-2">Sample keys:</span>
                        <div className="font-mono text-slate-300 bg-slate-900/80 px-3 py-2 rounded-lg border border-slate-700/50 text-xs">
                          {ownerLoadInfo.keys.join(', ')}
                        </div>
                      </div>
                    )}
                    {ownerLoadInfo.error && (
                      <div className="mt-3 pt-3 border-t border-slate-700/50">
                        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                          <span className="text-red-400 font-medium">Error: {ownerLoadInfo.error}</span>
                        </div>
                      </div>
                    )}
                    <div className="mt-5 pt-4 border-t border-slate-700/50 flex items-center gap-3">
                      <button
                        onClick={() => loadOwners()}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-500 to-blue-600 text-white text-sm font-semibold hover:from-blue-600 hover:to-blue-700 transition-all duration-200 shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 hover:scale-105"
                      >
                        <RefreshCw className="w-4 h-4" />
                        Load Owner Names
                      </button>
                      <span className="text-xs text-slate-500 italic">(manual, to avoid heavy DB load)</span>
                    </div>
                  </div>
                </div>
              </details>

              {/* Data Table */}
              <div className="overflow-auto rounded-xl border border-slate-700/50 bg-slate-900/20">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-24">
                    <div className="relative">
                      <div className="absolute inset-0 bg-blue-500/20 blur-2xl rounded-full" />
                      <RefreshCw className="relative w-16 h-16 text-blue-400 animate-spin mb-6" />
                    </div>
                    <p className="text-slate-400 text-xl font-medium">Loading rows...</p>
                    <p className="text-slate-500 text-sm mt-2">Please wait while we fetch the data</p>
                  </div>
                ) : (
                  <AdminDataTable
                    tableName={selected ?? undefined}
                    columns={schema?.columns ?? []}
                    rows={rows}
                    ownerMap={ownerMap}
                    page={page}
                    pageSize={pageSize}
                    total={total}
                    onPageChange={(p) => setPage(p)}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )

  // Render Stats Tab Content
  const renderStatsContent = () => (
    <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl p-4 sm:p-6">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />
      <div className="relative">
        <DatabaseStatsCards autoRefresh={true} refreshInterval={30000} />
      </div>
    </div>
  )

  // Render Storage Tab Content
  const renderStorageContent = () => (
    <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl p-4 sm:p-6">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />
      <div className="relative">
        <StorageAnalysisChart />
      </div>
    </div>
  )

  // Render History Tab Content
  const renderHistoryContent = () => (
    <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl p-4 sm:p-6">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />
      <div className="relative">
        <MonitoringHistoryViewer />
      </div>
    </div>
  )

  // Render Maintenance Tab Content
  const renderMaintenanceContent = () => (
    <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl p-4 sm:p-6">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />
      <div className="relative">
        <MaintenanceTools />
      </div>
    </div>
  )

  // Render active tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case 'tables':
        return renderTablesContent()
      case 'stats':
        return renderStatsContent()
      case 'storage':
        return renderStorageContent()
      case 'history':
        return renderHistoryContent()
      case 'maintenance':
        return renderMaintenanceContent()
      default:
        return null
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-900 to-black">
      <div className="max-w-[1800px] mx-auto p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent mb-2 sm:mb-3">
            Database Management
          </h1>
          <p className="text-slate-400 text-sm sm:text-lg">Control database access, view statistics, and manage maintenance</p>
        </div>

        {/* Tab Navigation */}
        <div className="mb-6 sm:mb-8">
          <div className="flex flex-wrap gap-2 sm:gap-3 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 pb-2 sm:pb-0">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative inline-flex items-center gap-2 px-4 sm:px-6 py-2.5 sm:py-3 rounded-xl text-sm font-semibold transition-all duration-300 touch-manipulation active:scale-95 whitespace-nowrap min-h-[44px] ${
                    activeTab === tab.id
                      ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30'
                      : 'bg-slate-800/40 text-slate-300 border border-slate-700/50 hover:bg-slate-700/50 hover:border-slate-600/50 hover:text-white'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Tab Content */}
        {renderTabContent()}
      </div>
    </div>
  )
}
