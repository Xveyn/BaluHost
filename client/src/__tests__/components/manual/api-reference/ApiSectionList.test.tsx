import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiSectionList } from '../../../../components/manual/api-reference/ApiSectionList'
import type { ApiSection } from '../../../../data/api-endpoints/types'

const t = (k: string) => k
const sections: ApiSection[] = [{
  title: 'Files', icon: null,
  endpoints: [{ method: 'GET', path: '/api/files/list', description: 'List', requiresAuth: false }],
}]

describe('ApiSectionList', () => {
  it('renders a section header and its endpoint cards', () => {
    render(<ApiSectionList sections={sections} rateLimits={{}} t={t} />)
    expect(screen.getByText('Files')).toBeInTheDocument()
    expect(screen.getByText('/api/files/list')).toBeInTheDocument()
  })
})
