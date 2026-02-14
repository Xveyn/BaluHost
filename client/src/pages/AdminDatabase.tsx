import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import useAdminDb from '../hooks/useAdminDb'
import AdminDataTable from '../components/AdminDataTable'
import ColumnFilterPanel from '../components/admin/ColumnFilterPanel'
import TableSelector from '../components/admin/TableSelector'
import { rowsToCsv } from '../lib/csv'
import type { ColumnFilters, AdminTableSchemaField } from '../lib/api'
import { Database, Table, Download, ChevronLeft, ChevronRight, RefreshCw, BarChart3, History, Wrench, Search, Filter, X, ChevronDown } from 'lucide-react'
import DatabaseStatsCards from '../components/admin/DatabaseStatsCards'
import MaintenanceTools from '../components/admin/MaintenanceTools'
import StorageAnalysisChart from '../components/admin/StorageAnalysisChart'
import MonitoringHistoryViewer from '../components/admin/MonitoringHistoryViewer'

type TabType = 'tables' | 'stats' | 'storage' | 'history' | 'maintenance'

export default function AdminDatabase() {
  const { t } = useTranslation('admin');
  const [activeTab, setActiveTab] = useState<TabType>('tables')
  const [tables, setTables] = useState<string[]>([])
  const [tableCategories, setTableCategories] = useState<Record<string, string[]>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [pageSize] = useState<number>(50)

  // Sort state
  const [sortBy, setSortBy] = useState<string | null>(null)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')

  // Filter state
  const [filters, setFilters] = useState<ColumnFilters>({})
  const [showFilters, setShowFilters] = useState(false)

  // Global search
  const [globalSearch, setGlobalSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const tabs = [
    { id: 'tables' as TabType, label: t('database.tabs.tables'), icon: Table },
    { id: 'stats' as TabType, label: t('database.tabs.stats'), icon: BarChart3 },
    { id: 'storage' as TabType, label: t('database.tabs.storage'), icon: Database },
    { id: 'history' as TabType, label: t('database.tabs.history'), icon: History },
    { id: 'maintenance' as TabType, label: t('database.tabs.maintenance'), icon: Wrench },
  ];

  const { fetchTables, fetchTableCategories, fetchSchema, fetchRows } = useAdminDb()
  const [schema, setSchema] = useState<any | null>(null)
  const [rows, setRows] = useState<any[]>([])
  const [ownerMap, setOwnerMap] = useState<Record<string,string>>({})
  const [ownerLoadInfo, setOwnerLoadInfo] = useState<{status: 'idle'|'loading'|'loaded'|'failed', page_size?: number, count?: number, keys?: string[], error?: string}>({status: 'idle'})
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [showSchema, setShowSchema] = useState(false)

  const totalPages = total ? Math.ceil((total ?? 0) / pageSize) : null
  const activeFilterCount = Object.keys(filters).length

  // Debounce global search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(globalSearch)
      setPage(1)
    }, 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [globalSearch])

  // Load tables and categories
  useEffect(() => {
    let mounted = true
    setError(null)
    Promise.all([fetchTables(), fetchTableCategories()])
      .then(([t, cat]) => {
        if (!mounted) return
        setTables(t)
        setTableCategories(cat.categories || {})
      })
      .catch((e) => {
        console.error('Failed to load admin tables', e)
        if (mounted) setError('Failed to load tables')
      })
    return () => { mounted = false }
  }, [])

  // Load rows when selection, page, sort, filter, or search changes
  useEffect(() => {
    if (!selected) return
    let mounted = true
    setLoading(true)
    setError(null)

    const sortByParam = sortBy || undefined
    const sortOrderParam = sortBy ? sortOrder : undefined
    const filtersParam = activeFilterCount > 0 ? filters : undefined
    const qParam = debouncedSearch || undefined

    Promise.all([fetchSchema(selected), fetchRows(selected, page, pageSize, undefined, qParam, sortByParam, sortOrderParam, filtersParam)])
      .then(([s, r]) => {
        if (!mounted) return
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
  }, [selected, page, pageSize, sortBy, sortOrder, filters, debouncedSearch])

  const handleTableSelect = (tableName: string) => {
    setSelected(tableName)
    setPage(1)
    setSortBy(null)
    setSortOrder('asc')
    setFilters({})
    setGlobalSearch('')
    setDebouncedSearch('')
    setShowFilters(false)
  }

  const handleSortChange = useCallback((column: string, order: 'asc' | 'desc') => {
    setSortBy(column)
    setSortOrder(order)
    setPage(1)
  }, [])

  const handleFiltersChange = useCallback((newFilters: ColumnFilters) => {
    setFilters(newFilters)
    setPage(1)
  }, [])

  // Manual owner mapping loader
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
    <div className="relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent pointer-events-none" />

      {/* Compact Toolbar */}
      <div className="relative px-4 sm:px-5 py-3 border-b border-slate-700/50 bg-slate-800/30">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Table Selector Dropdown */}
          <TableSelector
            tables={tables}
            categories={tableCategories}
            selected={selected}
            onSelect={handleTableSelect}
          />

          {/* Global Search */}
          {selected && (
            <div className="relative flex-1 min-w-[160px] max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
                placeholder="Search columns..."
                className="w-full bg-slate-800/60 border border-slate-700/50 rounded-lg pl-8 pr-8 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
              />
              {globalSearch && (
                <button
                  onClick={() => { setGlobalSearch(''); setDebouncedSearch('') }}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Filter Toggle */}
          {selected && schema?.columns?.length > 0 && (
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 border ${
                showFilters || activeFilterCount > 0
                  ? 'bg-blue-500/10 border-blue-500/40 text-blue-300'
                  : 'bg-slate-800/60 border-slate-700/50 text-slate-300 hover:bg-slate-700/50 hover:text-white'
              }`}
            >
              <Filter className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Filters</span>
              {activeFilterCount > 0 && (
                <span className="bg-blue-500 text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </button>
          )}

          {/* Pagination */}
          {selected && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                className={`p-1.5 rounded-md border transition-all duration-200 ${
                  page <= 1
                    ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                    : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:text-white'
                }`}
                disabled={page <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-slate-300 font-medium min-w-[60px] text-center tabular-nums">
                {page}{totalPages ? ` / ${totalPages}` : ''}
              </span>
              <button
                onClick={() => setPage(page + 1)}
                className={`p-1.5 rounded-md border transition-all duration-200 ${
                  totalPages !== null && page >= (totalPages ?? 1)
                    ? 'border-slate-700/50 bg-slate-800/40 text-slate-500 cursor-not-allowed'
                    : 'border-slate-600/50 bg-slate-700/40 text-slate-200 hover:bg-slate-700 hover:text-white'
                }`}
                disabled={totalPages !== null && page >= (totalPages ?? 1)}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Export Button */}
          <button
            disabled={!selected || rows.length === 0}
            className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 ${
              selected && rows.length
                ? 'bg-blue-500/20 border border-blue-500/40 text-blue-300 hover:bg-blue-500/30'
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
            <Download className="w-3.5 h-3.5" />
            CSV
          </button>

          {/* Compact info */}
          {selected && total !== null && (
            <span className="text-[11px] text-slate-500 ml-auto hidden sm:inline tabular-nums">
              {total.toLocaleString()} rows · {schema?.columns?.length ?? 0} columns
            </span>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="relative">
        {!selected && (
          <div className="text-center py-16 px-4">
            <Database className="w-12 h-12 text-slate-700 mx-auto mb-4" />
            <p className="text-slate-400 text-sm font-medium">Select a table to view its data</p>
            <p className="text-slate-500 text-xs mt-1">{tables.length} tables available</p>
          </div>
        )}

        {selected && (
          <>
            {error && (
              <div className="mx-4 sm:mx-5 mt-4 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
                <p className="text-red-400 text-xs font-medium">{error}</p>
              </div>
            )}

            {/* Column Filter Panel */}
            {showFilters && schema?.columns && (
              <div className="mx-4 sm:mx-5 mt-4">
                <ColumnFilterPanel
                  columns={schema.columns as AdminTableSchemaField[]}
                  filters={filters}
                  onFiltersChange={handleFiltersChange}
                />
              </div>
            )}

            {/* Collapsible Schema Pills */}
            {schema?.columns && (
              <div className="mx-4 sm:mx-5 mt-4">
                <button
                  onClick={() => setShowSchema(!showSchema)}
                  className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showSchema ? '' : '-rotate-90'}`} />
                  Schema ({schema.columns.length} columns)
                </button>
                {showSchema && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(schema.columns as AdminTableSchemaField[]).map((col) => (
                      <span
                        key={col.name}
                        className={`inline-flex items-center gap-1 bg-slate-800/60 border border-slate-700/40 rounded-md px-2 py-1 text-xs ${
                          col.nullable ? 'opacity-70' : ''
                        }`}
                      >
                        <span className="text-slate-300">{col.name}</span>
                        <span className="text-slate-500">:</span>
                        <span className="text-slate-500 text-[10px] uppercase">{col.type}</span>
                        {col.nullable && <span className="text-slate-600 text-[10px]">?</span>}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Owner Mapping - compact */}
            <details className="mx-4 sm:mx-5 mt-4 group">
              <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1.5">
                <ChevronDown className="w-3.5 h-3.5 -rotate-90 group-open:rotate-0 transition-transform" />
                Owner Mapping
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  ownerLoadInfo.status === 'loaded' ? 'bg-emerald-500/20 text-emerald-400' :
                  ownerLoadInfo.status === 'loading' ? 'bg-blue-500/20 text-blue-400' :
                  ownerLoadInfo.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                  'bg-slate-700/50 text-slate-500'
                }`}>
                  {ownerLoadInfo.status}
                </span>
              </summary>
              <div className="mt-2 pl-5 pb-2 space-y-2 text-xs">
                {ownerLoadInfo.count !== undefined && (
                  <p className="text-slate-500">{ownerLoadInfo.count} users loaded</p>
                )}
                {ownerLoadInfo.error && (
                  <p className="text-red-400">Error: {ownerLoadInfo.error}</p>
                )}
                <button
                  onClick={() => loadOwners()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800/60 border border-slate-700/50 text-slate-300 hover:text-white hover:border-slate-600/50 transition-colors text-xs"
                >
                  <RefreshCw className={`w-3 h-3 ${ownerLoadInfo.status === 'loading' ? 'animate-spin' : ''}`} />
                  Load Owner Names
                </button>
              </div>
            </details>

            {/* Data Table */}
            <div className="mt-4">
              {loading ? (
                <div className="flex items-center justify-center py-16 gap-3">
                  <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
                  <span className="text-slate-400 text-sm">Loading rows...</span>
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
                  sortBy={sortBy}
                  sortOrder={sortOrder}
                  onSortChange={handleSortChange}
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
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
                  <span className="hidden sm:inline">{tab.label}</span>
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
