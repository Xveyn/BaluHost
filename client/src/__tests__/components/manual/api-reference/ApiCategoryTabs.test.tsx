import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ApiCategoryTabs } from '../../../../components/manual/api-reference/ApiCategoryTabs'
import type { ApiSection } from '../../../../data/api-endpoints/types'
import type { ApiCategory } from '../../../../lib/openapi-transform'

const t = (k: string) => k
const section = (title: string): ApiSection => ({ title, icon: null, endpoints: [
  { method: 'GET', path: `/api/${title}`, description: '', requiresAuth: false },
] })
const apiSections: ApiSection[] = [section('files'), section('auth')]
const apiCategories: ApiCategory[] = [{ id: 'core', label: 'Core', sections: [section('files')] }]

describe('ApiCategoryTabs', () => {
  it('renders the "all" pill with the total endpoint count and per-category pills', () => {
    render(<ApiCategoryTabs apiSections={apiSections} apiCategories={apiCategories}
      selectedCategory={null} selectedSection={null} currentCategorySections={[]}
      onSelectCategory={vi.fn()} onSelectSection={vi.fn()} t={t} />)
    expect(screen.getByText('Core')).toBeInTheDocument()
    expect(screen.getByText('(2)')).toBeInTheDocument() // total endpoints across all sections
  })

  it('calls onSelectCategory when a category pill is clicked', () => {
    const onSelectCategory = vi.fn()
    render(<ApiCategoryTabs apiSections={apiSections} apiCategories={apiCategories}
      selectedCategory={null} selectedSection={null} currentCategorySections={[]}
      onSelectCategory={onSelectCategory} onSelectSection={vi.fn()} t={t} />)
    fireEvent.click(screen.getByText('Core'))
    expect(onSelectCategory).toHaveBeenCalledWith('core')
  })
})
