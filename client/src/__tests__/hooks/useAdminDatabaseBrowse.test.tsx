import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { createQueryWrapper } from '../helpers/queryClient'
import { useAdminDatabaseBrowse } from '../../hooks/useAdminDatabaseBrowse'
import * as adminDbApi from '../../api/admin-db'
import type { AdminTableRowsResponse, AdminTableSchemaResponse } from '../../api/admin-db'

vi.mock('../../api/admin-db')
const api = vi.mocked(adminDbApi)

const schema: AdminTableSchemaResponse = {
  table: 'users',
  columns: [{ name: 'id', type: 'int', nullable: false }, { name: 'username', type: 'str', nullable: true }],
}

const rows: AdminTableRowsResponse = {
  table: 'users',
  page: 1,
  page_size: 25,
  rows: [{ id: 1, username: 'alice' }, { id: 2, username: 'bob' }],
  total: 130,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getAdminTables.mockResolvedValue(['users', 'shares'])
  api.getAdminTableCategories.mockResolvedValue({ categories: { core: ['users', 'shares'] } })
  api.getAdminTableSchema.mockResolvedValue(schema)
  api.getAdminTableRows.mockResolvedValue(rows)
})

function setup() {
  return renderHook(() => useAdminDatabaseBrowse(), { wrapper: createQueryWrapper() })
}

describe('useAdminDatabaseBrowse — selection + derived values', () => {
  it('exposes the loaded table list and starts with no selection', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toEqual(['users', 'shares']))
    expect(result.current.selected).toBeNull()
    expect(result.current.page).toBe(1)
    expect(result.current.pageSize).toBe(25)
  })

  it('handleTableSelect selects and resets page/sort/filters/search/detail', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    act(() => { result.current.setPage(5) })
    act(() => { result.current.handleSortChange('id', 'desc') })
    act(() => { result.current.handleFiltersChange({ id: { op: 'eq', value: 1 } }) })
    act(() => { result.current.setShowFilters(true) })
    expect(result.current.activeFilterCount).toBe(1)

    act(() => { result.current.handleTableSelect('users') })
    expect(result.current.selected).toBe('users')
    expect(result.current.page).toBe(1)
    expect(result.current.sortBy).toBeNull()
    expect(result.current.sortOrder).toBeNull()
    expect(result.current.filters).toEqual({})
    expect(result.current.activeFilterCount).toBe(0)
    expect(result.current.showFilters).toBe(false)
    expect(result.current.selectedRow).toBeNull()
    expect(result.current.globalSearch).toBe('')
  })

  it('derives schema/rows/total/totalPages and the row range once a table is loaded', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    act(() => { result.current.handleTableSelect('users') })
    await waitFor(() => expect(result.current.total).toBe(130))

    expect(result.current.rows).toHaveLength(2)
    expect(result.current.schema?.columns).toHaveLength(2)
    // 130 rows / 25 per page → 6 pages
    expect(result.current.totalPages).toBe(6)
    // page 1: rows 1–25
    expect(result.current.rangeStart).toBe(1)
    expect(result.current.rangeEnd).toBe(25)
  })

  it('handleSortChange and handleFiltersChange reset to page 1', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    act(() => { result.current.setPage(4) })
    act(() => { result.current.handleSortChange('id', 'asc') })
    expect(result.current.page).toBe(1)

    act(() => { result.current.setPage(4) })
    act(() => { result.current.handleFiltersChange({ id: { op: 'gt', value: 3 } }) })
    expect(result.current.page).toBe(1)
    expect(result.current.activeFilterCount).toBe(1)
  })

  it('handleRowClick toggles the selected row', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))
    const row = { id: 9 }

    act(() => { result.current.handleRowClick(row) })
    expect(result.current.selectedRow).toBe(row)
    act(() => { result.current.handleRowClick(row) })
    expect(result.current.selectedRow).toBeNull()
  })

  it('clearGlobalSearch empties the search box', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))
    act(() => { result.current.setGlobalSearch('foo') })
    expect(result.current.globalSearch).toBe('foo')
    act(() => { result.current.clearGlobalSearch() })
    expect(result.current.globalSearch).toBe('')
  })
})

describe('useAdminDatabaseBrowse — loadOwners', () => {
  it('loads the owner map on the first successful page size', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    await act(async () => { await result.current.loadOwners() })

    expect(result.current.ownerLoadInfo.status).toBe('loaded')
    expect(result.current.ownerLoadInfo.page_size).toBe(2000)
    expect(result.current.ownerMap).toEqual({ '1': 'alice', '2': 'bob' })
    // first attempt is the largest page size
    expect(api.getAdminTableRows).toHaveBeenCalledWith('users', 1, 2000)
  })

  it('falls back through page sizes on 422, succeeding at a smaller size', async () => {
    api.getAdminTableRows
      .mockRejectedValueOnce({ response: { status: 422 } }) // 2000
      .mockRejectedValueOnce({ response: { status: 422 } }) // 1000
      .mockResolvedValueOnce(rows)                          // 500
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    await act(async () => { await result.current.loadOwners() })

    expect(result.current.ownerLoadInfo.status).toBe('loaded')
    expect(result.current.ownerLoadInfo.page_size).toBe(500)
    expect(api.getAdminTableRows).toHaveBeenNthCalledWith(3, 'users', 1, 500)
  })

  it('aborts the ladder on a non-422 HTTP error after the first attempt', async () => {
    api.getAdminTableRows.mockRejectedValue({ response: { status: 500 } })
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    await act(async () => { await result.current.loadOwners() })

    expect(result.current.ownerLoadInfo.status).toBe('failed')
    // Pre-existing quirk (preserved verbatim from the original): the non-422
    // branch briefly sets `HTTP 500` then breaks, but because `successful` is
    // still false the post-loop guard overwrites it with the generic message.
    expect(result.current.ownerLoadInfo.error).toBe('no successful response')
    // stopped after the first attempt (broke out of the size ladder)
    expect(api.getAdminTableRows).toHaveBeenCalledTimes(1)
  })

  it('fails fast when the users table is not available', async () => {
    api.getAdminTables.mockResolvedValue(['shares'])
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toEqual(['shares']))

    await act(async () => { await result.current.loadOwners() })

    expect(result.current.ownerLoadInfo.status).toBe('failed')
    expect(result.current.ownerLoadInfo.error).toBe('users table not available')
    expect(api.getAdminTableRows).not.toHaveBeenCalled()
  })
})

describe('useAdminDatabaseBrowse — handleCsvExport', () => {
  it('is a no-op when nothing is selected or there are no rows', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = createObjectURL
    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))

    // nothing selected → early return, no blob created
    act(() => { result.current.handleCsvExport() })
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('builds and triggers a CSV download once a table with rows is loaded', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    // jsdom lacks these
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = createObjectURL
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeObjectURL
    const clickSpy = vi.fn()
    const anchor = document.createElement('a')
    anchor.click = clickSpy
    const createEl = vi.spyOn(document, 'createElement').mockReturnValue(anchor)

    const { result } = setup()
    await waitFor(() => expect(result.current.tables).toContain('users'))
    act(() => { result.current.handleTableSelect('users') })
    await waitFor(() => expect(result.current.rows).toHaveLength(2))

    act(() => { result.current.handleCsvExport() })

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(anchor.download).toBe('users.csv')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock')
    createEl.mockRestore()
  })
})
