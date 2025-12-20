import { describe, it, expect } from 'vitest'
import { rowsToCsv } from '../lib/csv'

describe('rowsToCsv', () => {
  it('converts rows to CSV with header', () => {
    const rows = [
      { id: 1, name: 'Alice', note: 'Hello' },
      { id: 2, name: 'Bob', note: 'He said "Hi"' }
    ]
    const csv = rowsToCsv(rows, ['id', 'name', 'note'])
    const lines = csv.split('\n')
    expect(lines[0]).toBe('id,name,note')
    expect(lines[1]).toContain('Alice')
    expect(lines[2]).toContain('"He said ""Hi"""')
  })
})
