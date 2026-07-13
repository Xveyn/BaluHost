import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EndpointCard } from '../../../../components/manual/api-reference/EndpointCard'
import type { ApiEndpoint } from '../../../../data/api-endpoints'

const t = (k: string) => k
const endpoint: ApiEndpoint = {
  method: 'POST', path: '/api/auth/login', description: 'Log in',
  requiresAuth: true,
  params: [], body: [], response: '{"token":"x"}',
} as ApiEndpoint

describe('EndpointCard', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
  })

  it('renders method, path and the auth shield', () => {
    render(<EndpointCard endpoint={endpoint} rateLimits={{}} t={t} />)
    expect(screen.getByText('POST')).toBeInTheDocument()
    expect(screen.getByText('/api/auth/login')).toBeInTheDocument()
    expect(screen.getByTitle('system:apiCenter.authRequired')).toBeInTheDocument()
  })

  it('shows the rate-limit badge when a matching config exists', () => {
    const rl = {
      auth_login: { id: 1, endpoint_type: 'auth_login', limit_string: '5/min',
        description: null, enabled: true, created_at: '', updated_at: null, updated_by: null },
    }
    render(<EndpointCard endpoint={endpoint} rateLimits={rl} t={t} />)
    expect(screen.getByText('5/min')).toBeInTheDocument()
  })

  it('expands to show the response and copies it', () => {
    render(<EndpointCard endpoint={endpoint} rateLimits={{}} t={t} />)
    // collapsed: response not shown
    expect(screen.queryByText('{"token":"x"}')).toBeNull()
    fireEvent.click(screen.getByText('/api/auth/login'))
    expect(screen.getByText('{"token":"x"}')).toBeInTheDocument()
    // after expansion the copy button is the only <button> in the card
    // (the header toggle is a <div onClick>, not a button)
    fireEvent.click(screen.getByRole('button'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('{"token":"x"}')
  })
})
