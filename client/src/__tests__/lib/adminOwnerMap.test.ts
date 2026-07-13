import { describe, it, expect } from 'vitest'
import { buildOwnerMap } from '../../lib/adminOwnerMap'

describe('buildOwnerMap', () => {
  it('maps id → username for standard rows', () => {
    const rows = [
      { id: 1, username: 'alice' },
      { id: 2, username: 'bob' },
    ]
    expect(buildOwnerMap(rows)).toEqual({ '1': 'alice', '2': 'bob' })
  })

  it('honours id key precedence id > ID > user_id > userId', () => {
    expect(buildOwnerMap([{ ID: 5, username: 'a' }])).toEqual({ '5': 'a' })
    expect(buildOwnerMap([{ user_id: 7, username: 'b' }])).toEqual({ '7': 'b' })
    expect(buildOwnerMap([{ userId: 9, username: 'c' }])).toEqual({ '9': 'c' })
    // id wins over the others when several are present
    expect(buildOwnerMap([{ id: 1, ID: 2, user_id: 3, username: 'x' }])).toEqual({ '1': 'x' })
  })

  it('honours name key precedence username > user_name > name > display_name > displayName', () => {
    expect(buildOwnerMap([{ id: 1, user_name: 'un' }])).toEqual({ '1': 'un' })
    expect(buildOwnerMap([{ id: 1, name: 'nm' }])).toEqual({ '1': 'nm' })
    expect(buildOwnerMap([{ id: 1, display_name: 'dn' }])).toEqual({ '1': 'dn' })
    expect(buildOwnerMap([{ id: 1, displayName: 'dN' }])).toEqual({ '1': 'dN' })
    expect(buildOwnerMap([{ id: 1, username: 'u', name: 'n' }])).toEqual({ '1': 'u' })
  })

  it('falls back to empty-string name when no name field present', () => {
    expect(buildOwnerMap([{ id: 42 }])).toEqual({ '42': '' })
  })

  it('skips rows whose coalesced id is undefined (preserves original guard)', () => {
    expect(buildOwnerMap([{ username: 'no-id' }])).toEqual({})
    // `id: null` with no other id field → the `??` chain falls through to
    // undefined → row is skipped.
    expect(buildOwnerMap([{ id: null, username: 'null-id' }])).toEqual({})
  })

  it('maps under the "null" key only when the coalesced id is literally null', () => {
    // The last fallback `userId` being null makes the coalesced id null (not
    // undefined), so the `id !== undefined` guard passes.
    expect(buildOwnerMap([{ userId: null, username: 'x' }])).toEqual({ 'null': 'x' })
  })

  it('stringifies numeric ids and tolerates empty / missing input', () => {
    expect(buildOwnerMap([])).toEqual({})
    expect(buildOwnerMap(undefined as unknown as Array<Record<string, unknown>>)).toEqual({})
  })
})
