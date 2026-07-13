import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

// Controlled schema so the hook doesn't hit /openapi.json.
const mkSection = (title: string, paths: string[]) => ({
  title, icon: null,
  endpoints: paths.map(p => ({ method: 'GET', path: p, description: `${p} desc`, requiresAuth: false })),
})
const SECTIONS = [mkSection('Files', ['/api/files/list']), mkSection('Auth', ['/api/auth/me'])]
const CATEGORIES = [{ id: 'core', label: 'Core', sections: [SECTIONS[0]] }]

vi.mock('../../hooks/useOpenApiSchema', () => ({
  useOpenApiSchema: () => ({
    sections: SECTIONS, categories: CATEGORIES,
    loading: false, error: null, refetch: vi.fn(),
  }),
}))

import { useApiReference } from '../../hooks/useApiReference'

describe('useApiReference', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('non-admin skips the rate-limit fetch and clears loading', async () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: 't' }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetch).not.toHaveBeenCalled()
    expect(result.current.rateLimits).toEqual({})
  })

  it('admin loads rate limits and maps them by endpoint_type', async () => {
    const configs = [
      { id: 1, endpoint_type: 'auth_login', limit_string: '5/min', description: null,
        enabled: true, created_at: '', updated_at: null, updated_by: null },
    ]
    ;(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true, json: async () => ({ configs }),
    })
    const { result } = renderHook(() => useApiReference({ isAdmin: true, token: 'tok' }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(result.current.rateLimits.auth_login.limit_string).toBe('5/min')
  })

  it('visibleSections: no filter returns all sections', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files', 'Auth'])
  })

  it('visibleSections: search filters endpoints by path/description', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    act(() => result.current.setSearchQuery('files'))
    // only the "Files" section survives the /api/files/list path match
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files'])
  })

  it('visibleSections: selecting a category narrows to its sections', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    act(() => result.current.setSelectedCategory('core'))
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files'])
  })
})
