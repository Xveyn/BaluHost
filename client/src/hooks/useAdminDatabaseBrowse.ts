import { useState, useEffect, useRef, useCallback } from 'react'
import { useAdminTables, useAdminTableData } from './useAdminDb'
import { getAdminTableRows } from '../api/admin-db'
import { buildOwnerMap } from '../lib/adminOwnerMap'
import { rowsToCsv } from '../lib/csv'
import type { ColumnFilters, AdminTableSchemaField } from '../api/admin-db'

export type OwnerLoadStatus = 'idle' | 'loading' | 'loaded' | 'failed'

export interface OwnerLoadInfo {
  status: OwnerLoadStatus
  page_size?: number
  count?: number
  keys?: string[]
  error?: string
}

/**
 * State + data logic for the AdminDatabase "browse" view.
 *
 * Extracted from `pages/AdminDatabase.tsx` verbatim (behaviour-preserving) so
 * the page becomes a thin orchestrator. Owns the selected-table browse state,
 * both react-query hooks, all derived values, the browse handlers, the manual
 * owner-map loader (with its page-size fallback ladder) and the CSV export.
 */
export function useAdminDatabaseBrowse() {
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(25)

  // Sort state
  const [sortBy, setSortBy] = useState<string | null>(null)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | null>(null)

  // Filter state
  const [filters, setFilters] = useState<ColumnFilters>({})
  const [showFilters, setShowFilters] = useState(false)

  // Global search
  const [globalSearch, setGlobalSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Mount guard for async handlers that aren't tied to an effect teardown
  // (e.g. the manual loadOwners button). Flipped to false on unmount.
  const isMountedRef = useRef(true)
  useEffect(() => {
    return () => { isMountedRef.current = false }
  }, [])

  // Row detail
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null)

  const [ownerMap, setOwnerMap] = useState<Record<string, string>>({})
  const [ownerLoadInfo, setOwnerLoadInfo] = useState<OwnerLoadInfo>({ status: 'idle' })

  const activeFilterCount = Object.keys(filters).length

  // Table list + categories (loaded once).
  const tablesQuery = useAdminTables()
  const tables = tablesQuery.data?.tables ?? []
  const tableCategories = tablesQuery.data?.categories ?? {}

  // Schema + rows for the selected table — key-driven refetch on any browse param.
  const tableDataQuery = useAdminTableData(selected, {
    page,
    pageSize,
    q: debouncedSearch || undefined,
    sortBy: sortBy || undefined,
    sortOrder: sortBy && sortOrder ? sortOrder : undefined,
    filters: activeFilterCount > 0 ? filters : undefined,
  })
  const schema: { columns?: AdminTableSchemaField[] } | null = tableDataQuery.data?.schema ?? null
  const rows: Record<string, unknown>[] = tableDataQuery.data?.rows.rows ?? []
  const total: number | null = tableDataQuery.data?.rows.total ?? null
  const loading = tableDataQuery.isLoading && selected !== null
  const error = tableDataQuery.isError
    ? 'Fehler beim Laden der Tabellendaten'
    : tablesQuery.isError
      ? 'Failed to load tables'
      : null

  const totalPages = total ? Math.ceil((total ?? 0) / pageSize) : null

  // Row range display
  const rangeStart = total !== null && total > 0 ? (page - 1) * pageSize + 1 : 0
  const rangeEnd = total !== null ? Math.min(page * pageSize, total) : 0

  // Debounce global search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(globalSearch)
      setPage(1)
    }, 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [globalSearch])

  const handleTableSelect = useCallback((tableName: string) => {
    setSelected(tableName)
    setPage(1)
    setSortBy(null)
    setSortOrder(null)
    setFilters({})
    setGlobalSearch('')
    setDebouncedSearch('')
    setShowFilters(false)
    setSelectedRow(null)
  }, [])

  const handleSortChange = useCallback((column: string | null, order: 'asc' | 'desc' | null) => {
    setSortBy(column)
    setSortOrder(order)
    setPage(1)
  }, [])

  const handleFiltersChange = useCallback((newFilters: ColumnFilters) => {
    setFilters(newFilters)
    setPage(1)
  }, [])

  const handleRowClick = useCallback((row: Record<string, unknown>) => {
    setSelectedRow(prev => prev === row ? null : row)
  }, [])

  // Clears the search box (and its debounced mirror) immediately.
  const clearGlobalSearch = useCallback(() => {
    setGlobalSearch('')
    setDebouncedSearch('')
  }, [])

  // Manual owner mapping loader (plain function, as in the original — not
  // memoized because it closes over the per-render `tables` array).
  const loadOwners = async () => {
    if (!tables.includes('users')) {
      setOwnerLoadInfo({ status: 'failed', error: 'users table not available' })
      return
    }
    setOwnerLoadInfo({ status: 'loading' })
    try {
      const sizes = [2000, 1000, 500, 200, 100, 50]
      let successful = false
      for (const sz of sizes) {
        try {
          const res = await getAdminTableRows('users', 1, sz)
          if (!isMountedRef.current) return
          const map = buildOwnerMap(res.rows || [])
          setOwnerMap(map)
          setOwnerLoadInfo({ status: 'loaded', page_size: sz, count: (res.rows || []).length, keys: Object.keys(map).slice(0, 20) })
          successful = true
          break
        } catch (err: unknown) {
          if (!isMountedRef.current) return
          const status = (err as { response?: { status?: number } })?.response?.status
          if (status && status !== 422) {
            setOwnerLoadInfo({ status: 'failed', error: `HTTP ${status}` })
            break
          }
          setOwnerLoadInfo({ status: 'loading', page_size: sz })
        }
      }
      if (!isMountedRef.current) return
      if (!successful) setOwnerLoadInfo({ status: 'failed', error: 'no successful response' })
    } catch (e: unknown) {
      if (!isMountedRef.current) return
      setOwnerLoadInfo({ status: 'failed', error: String(e) })
    }
  }

  const handleCsvExport = () => {
    if (!selected || rows.length === 0) return
    const cols = schema?.columns?.map((c: AdminTableSchemaField) => c.name) ?? []
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
  }

  return {
    // table list
    tables,
    tableCategories,
    // browse state
    selected,
    page,
    setPage,
    pageSize,
    setPageSize,
    sortBy,
    sortOrder,
    filters,
    showFilters,
    setShowFilters,
    globalSearch,
    setGlobalSearch,
    clearGlobalSearch,
    selectedRow,
    setSelectedRow,
    ownerMap,
    ownerLoadInfo,
    // derived
    schema,
    rows,
    total,
    loading,
    error,
    totalPages,
    rangeStart,
    rangeEnd,
    activeFilterCount,
    // handlers
    handleTableSelect,
    handleSortChange,
    handleFiltersChange,
    handleRowClick,
    loadOwners,
    handleCsvExport,
  }
}
