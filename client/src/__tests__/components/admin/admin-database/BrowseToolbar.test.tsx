import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../../../../components/admin/TableSelector', () => ({
  default: () => <div data-testid="table-selector" />,
}))

import BrowseToolbar from '../../../../components/admin/admin-database/BrowseToolbar'

const baseProps = {
  tables: ['users', 'shares'],
  categories: { core: ['users', 'shares'] },
  selected: 'users' as string | null,
  onTableSelect: vi.fn(),
  globalSearch: '',
  onGlobalSearchChange: vi.fn(),
  onClearGlobalSearch: vi.fn(),
  columnCount: 3,
  showFilters: false,
  onToggleFilters: vi.fn(),
  activeFilterCount: 0,
  pageSize: 25,
  onPageSizeChange: vi.fn(),
  page: 1,
  totalPages: 6,
  onPageChange: vi.fn(),
  rowCount: 2,
  onCsvExport: vi.fn(),
  total: 130,
  rangeStart: 1,
  rangeEnd: 25,
}

function renderToolbar(overrides: Partial<typeof baseProps> = {}) {
  const props = { ...baseProps, ...overrides }
  return { props, ...render(<BrowseToolbar {...props} />) }
}

describe('BrowseToolbar — no table selected', () => {
  it('hides search / filter / pagination and disables CSV export', () => {
    renderToolbar({ selected: null, rowCount: 0, total: null })
    expect(screen.queryByPlaceholderText('Search columns...')).toBeNull()
    expect(screen.queryByRole('button', { name: /filters/i })).toBeNull()
    const csv = screen.getByRole('button', { name: /csv/i })
    expect((csv as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('BrowseToolbar — table selected', () => {
  it('fires onGlobalSearchChange while typing', () => {
    const { props } = renderToolbar()
    fireEvent.change(screen.getByPlaceholderText('Search columns...'), { target: { value: 'abc' } })
    expect(props.onGlobalSearchChange).toHaveBeenCalledWith('abc')
  })

  it('shows the clear button only when there is search text and fires onClearGlobalSearch', () => {
    const { props } = renderToolbar({ globalSearch: 'abc' })
    const buttons = screen.getAllByRole('button')
    // clear button is the icon-only button right after the search input
    fireEvent.click(buttons[0])
    expect(props.onClearGlobalSearch).toHaveBeenCalledTimes(1)
  })

  it('hides the filter toggle when there are no columns', () => {
    renderToolbar({ columnCount: 0 })
    expect(screen.queryByRole('button', { name: /filters/i })).toBeNull()
  })

  it('disables the prev button on page 1 and advances on next', () => {
    renderToolbar({ page: 1 })
    const prev = screen.getAllByRole('button').find(b => (b as HTMLButtonElement).disabled && b.querySelector('svg'))
    expect(prev).toBeTruthy()
    // next page button is enabled at page 1 of 6
    const pageLabel = screen.getByText('1 / 6')
    expect(pageLabel).toBeTruthy()
  })

  it('advances to the next page via onPageChange(page + 1)', () => {
    const { props } = renderToolbar({ page: 2 })
    // the two chevron buttons; the second is "next"
    const chevrons = screen.getAllByRole('button').filter(b => b.querySelector('svg') && !b.textContent?.trim())
    fireEvent.click(chevrons[chevrons.length - 1])
    expect(props.onPageChange).toHaveBeenCalledWith(3)
  })

  it('fires onPageSizeChange with the numeric size', () => {
    const { props } = renderToolbar()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '50' } })
    expect(props.onPageSizeChange).toHaveBeenCalledWith(50)
  })

  it('enables and fires CSV export when rows exist', () => {
    const { props } = renderToolbar()
    const csv = screen.getByRole('button', { name: /csv/i })
    expect((csv as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(csv)
    expect(props.onCsvExport).toHaveBeenCalledTimes(1)
  })

  it('renders the row-count readout with column count', () => {
    renderToolbar()
    expect(screen.getByText(/1–25 von 130 · 3 columns/)).toBeTruthy()
  })
})
