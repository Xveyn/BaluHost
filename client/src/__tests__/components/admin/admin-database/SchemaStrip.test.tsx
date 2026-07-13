import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SchemaStrip from '../../../../components/admin/admin-database/SchemaStrip'
import type { AdminTableSchemaField } from '../../../../api/admin-db'

const columns: AdminTableSchemaField[] = [
  { name: 'id', type: 'int', nullable: false },
  { name: 'email', type: 'str', nullable: true },
]

describe('SchemaStrip', () => {
  it('renders one badge per column with its name', () => {
    render(<SchemaStrip columns={columns} />)
    expect(screen.getByText('id')).toBeTruthy()
    expect(screen.getByText('email')).toBeTruthy()
  })

  it('marks nullable columns with a "?" hint and dims them', () => {
    const { container } = render(<SchemaStrip columns={columns} />)
    expect(screen.getByText('?')).toBeTruthy()
    // the nullable badge carries the opacity class
    expect(container.querySelector('.opacity-70')).toBeTruthy()
  })

  it('renders nothing but the wrapper for an empty column list', () => {
    const { container } = render(<SchemaStrip columns={[]} />)
    expect(container.querySelectorAll('span').length).toBe(0)
  })
})
