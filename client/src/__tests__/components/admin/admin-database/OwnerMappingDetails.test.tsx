import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import OwnerMappingDetails from '../../../../components/admin/admin-database/OwnerMappingDetails'

describe('OwnerMappingDetails', () => {
  it('shows the current status and calls onLoad when the button is clicked', () => {
    const onLoad = vi.fn()
    render(<OwnerMappingDetails ownerLoadInfo={{ status: 'idle' }} onLoad={onLoad} />)
    expect(screen.getByText('idle')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /load owner names/i }))
    expect(onLoad).toHaveBeenCalledTimes(1)
  })

  it('renders the loaded user count when present', () => {
    render(<OwnerMappingDetails ownerLoadInfo={{ status: 'loaded', count: 7 }} onLoad={vi.fn()} />)
    expect(screen.getByText('7 users loaded')).toBeTruthy()
  })

  it('renders an error line when the load failed', () => {
    render(<OwnerMappingDetails ownerLoadInfo={{ status: 'failed', error: 'HTTP 500' }} onLoad={vi.fn()} />)
    expect(screen.getByText('Error: HTTP 500')).toBeTruthy()
  })
})
