import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const stableT = (k: string) => k
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}))

import DatabaseCategoryNav from '../../../../components/admin/admin-database/DatabaseCategoryNav'

describe('DatabaseCategoryNav', () => {
  it('renders both category pills and fires onCategoryChange', () => {
    const onCategoryChange = vi.fn()
    render(
      <DatabaseCategoryNav
        activeCategory="browse"
        onCategoryChange={onCategoryChange}
        analyticsTab="stats"
        onAnalyticsTabChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /analytics/i }))
    expect(onCategoryChange).toHaveBeenCalledWith('analytics')
  })

  it('hides the analytics sub-tabs while Browse is active', () => {
    render(
      <DatabaseCategoryNav
        activeCategory="browse"
        onCategoryChange={vi.fn()}
        analyticsTab="stats"
        onAnalyticsTabChange={vi.fn()}
      />,
    )
    expect(screen.queryByText('database.tabs.storage')).toBeNull()
  })

  it('shows the analytics sub-tabs and fires onAnalyticsTabChange when Analytics is active', () => {
    const onAnalyticsTabChange = vi.fn()
    render(
      <DatabaseCategoryNav
        activeCategory="analytics"
        onCategoryChange={vi.fn()}
        analyticsTab="stats"
        onAnalyticsTabChange={onAnalyticsTabChange}
      />,
    )
    // all five sub-tabs rendered via the i18n keys
    expect(screen.getByText('database.tabs.stats')).toBeTruthy()
    expect(screen.getByText('database.tabs.retention')).toBeTruthy()
    fireEvent.click(screen.getByText('database.tabs.history'))
    expect(onAnalyticsTabChange).toHaveBeenCalledWith('history')
  })
})
