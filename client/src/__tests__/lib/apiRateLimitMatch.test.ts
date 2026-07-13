import { describe, it, expect } from 'vitest'
import { matchEndpointToRateLimitType } from '../../lib/apiRateLimitMatch'

describe('matchEndpointToRateLimitType', () => {
  it('matches specific auth endpoints before the auth catch-all', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/auth/login')).toBe('auth_login')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/register')).toBe('auth_register')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/change-password')).toBe('auth_password_change')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/refresh')).toBe('auth_refresh')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/verify-2fa')).toBe('auth_2fa_verify')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/2fa/setup')).toBe('auth_2fa_setup')
    // generic auth path falls through to the catch-all
    expect(matchEndpointToRateLimitType('GET', '/api/auth/me')).toBe('user_operations')
  })

  it('is case-insensitive on method and path', () => {
    expect(matchEndpointToRateLimitType('post', '/API/AUTH/LOGIN')).toBe('auth_login')
  })

  it('matches files specific-before-generic', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/files/upload/chunked/init')).toBe('file_chunked')
    expect(matchEndpointToRateLimitType('POST', '/api/files/upload')).toBe('file_upload')
    expect(matchEndpointToRateLimitType('GET', '/api/files/download/x')).toBe('file_download')
    expect(matchEndpointToRateLimitType('GET', '/api/files/list')).toBe('file_list')
    expect(matchEndpointToRateLimitType('DELETE', '/api/files/x')).toBe('file_delete')
    expect(matchEndpointToRateLimitType('PUT', '/api/files/x')).toBe('file_write')
  })

  it('matches activity as file_list', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/activity/feed')).toBe('file_list')
  })

  it('matches shares by write-method vs read', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/shares')).toBe('share_create')
    expect(matchEndpointToRateLimitType('PATCH', '/api/shares/1')).toBe('share_create')
    expect(matchEndpointToRateLimitType('DELETE', '/api/shares/1')).toBe('share_create')
    expect(matchEndpointToRateLimitType('GET', '/api/shares')).toBe('share_list')
  })

  it('matches mobile + desktop-pairing endpoints', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/register')).toBe('mobile_register')
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/token/generate')).toBe('mobile_register')
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/sync')).toBe('mobile_sync')
    expect(matchEndpointToRateLimitType('GET', '/api/mobile/upload-queue')).toBe('mobile_sync')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/device-code')).toBe('desktop_pairing_request')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/token')).toBe('desktop_pairing_poll')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/verify')).toBe('desktop_pairing_verify')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/approve')).toBe('desktop_pairing_approve')
  })

  it('matches vpn/backup/sync operation groups', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/vpn')).toBe('vpn_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/vpn/clients')).toBe('vpn_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/backup')).toBe('backup_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/sync/start')).toBe('sync_operations')
  })

  it('matches POST benchmark/run before the admin catch-all', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/benchmark/run')).toBe('admin_benchmark')
    // non-run benchmark falls to admin catch-all
    expect(matchEndpointToRateLimitType('GET', '/api/benchmark/history')).toBe('admin_operations')
  })

  it('matches api-keys and users groups', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/api-keys')).toBe('api_key_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/users')).toBe('user_operations')
  })

  it('splits system/monitoring/energy by GET vs write', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/system/info')).toBe('system_monitor')
    expect(matchEndpointToRateLimitType('POST', '/api/system/reboot')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/monitoring/cpu')).toBe('system_monitor')
    expect(matchEndpointToRateLimitType('GET', '/api/energy/stats')).toBe('system_monitor')
  })

  it('splits vcl and ssd-cache by GET vs write', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/vcl/versions')).toBe('file_list')
    expect(matchEndpointToRateLimitType('POST', '/api/vcl/restore')).toBe('file_write')
    expect(matchEndpointToRateLimitType('GET', '/api/ssd-cache/status')).toBe('file_list')
    expect(matchEndpointToRateLimitType('POST', '/api/ssd-cache/clear')).toBe('admin_operations')
  })

  it('matches admin-prefix catch-all', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/pihole/status')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/fans/config')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/updates/check')).toBe('admin_operations')
  })

  it('returns null for unmatched paths', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/unknown/x')).toBeNull()
    expect(matchEndpointToRateLimitType('GET', '/healthz')).toBeNull()
  })
})
