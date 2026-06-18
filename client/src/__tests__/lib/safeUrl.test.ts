import { describe, it, expect } from 'vitest'
import { safeExternalUrl } from '../../lib/safeUrl'

describe('safeExternalUrl', () => {
  it('accepts http and https URLs', () => {
    expect(safeExternalUrl('https://example.com/plugin')).toBe('https://example.com/plugin')
    expect(safeExternalUrl('http://example.com')).toBe('http://example.com/')
  })

  it('rejects javascript: URLs (JWT exfiltration vector)', () => {
    expect(safeExternalUrl('javascript:alert(document.cookie)')).toBeNull()
    expect(safeExternalUrl('JavaScript:void(0)')).toBeNull()
  })

  it('rejects data:, vbscript:, file: and other non-http(s) schemes', () => {
    expect(safeExternalUrl('data:text/html,<script>alert(1)</script>')).toBeNull()
    expect(safeExternalUrl('vbscript:msgbox(1)')).toBeNull()
    expect(safeExternalUrl('file:///etc/passwd')).toBeNull()
  })

  it('rejects whitespace/control-char obfuscation around the scheme', () => {
    expect(safeExternalUrl('\tjavascript:alert(1)')).toBeNull()
    expect(safeExternalUrl('  javascript:alert(1)')).toBeNull()
  })

  it('rejects relative URLs (no absolute scheme)', () => {
    expect(safeExternalUrl('/local/path')).toBeNull()
    expect(safeExternalUrl('example.com')).toBeNull()
  })

  it('returns null for empty/nullish input', () => {
    expect(safeExternalUrl(null)).toBeNull()
    expect(safeExternalUrl(undefined)).toBeNull()
    expect(safeExternalUrl('')).toBeNull()
    expect(safeExternalUrl('   ')).toBeNull()
  })
})
