export interface RateLimitConfig {
  id: number;
  endpoint_type: string;
  limit_string: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
  updated_by: number | null;
}

// ==================== Dynamic Rate Limit Matching ====================

/**
 * Dynamically match an API endpoint to its rate limit endpoint_type
 * based on HTTP method and path patterns (mirrors backend decorator usage).
 */
export function matchEndpointToRateLimitType(method: string, path: string): string | null {
  const p = path.toLowerCase();
  const m = method.toUpperCase();

  // Auth endpoints (most specific first)
  if (m === 'POST' && p === '/api/auth/login') return 'auth_login';
  if (m === 'POST' && p === '/api/auth/register') return 'auth_register';
  if (m === 'POST' && p === '/api/auth/change-password') return 'auth_password_change';
  if (m === 'POST' && p === '/api/auth/refresh') return 'auth_refresh';
  if (m === 'POST' && p === '/api/auth/verify-2fa') return 'auth_2fa_verify';
  if (m === 'POST' && p.startsWith('/api/auth/2fa/')) return 'auth_2fa_setup';
  if (p.startsWith('/api/auth/')) return 'user_operations';

  // Files (specific before generic)
  if (p.startsWith('/api/files/upload/chunked')) return 'file_chunked';
  if (m === 'POST' && p.startsWith('/api/files/upload')) return 'file_upload';
  if (m === 'GET' && p.startsWith('/api/files/download')) return 'file_download';
  if (m === 'GET' && p.startsWith('/api/files/list')) return 'file_list';
  if (m === 'DELETE' && p.startsWith('/api/files/')) return 'file_delete';
  if (p.startsWith('/api/files/')) return 'file_write';

  // Activity
  if (p.startsWith('/api/activity/')) return 'file_list';

  // Shares
  if (['POST', 'PATCH', 'DELETE'].includes(m) && p.startsWith('/api/shares')) return 'share_create';
  if (p.startsWith('/api/shares')) return 'share_list';

  // Mobile
  if (m === 'POST' && (p === '/api/mobile/register' || p === '/api/mobile/token/generate')) return 'mobile_register';
  if (p.includes('/mobile/sync') || p.includes('/mobile/upload-queue')) return 'mobile_sync';

  // Desktop pairing
  if (p.includes('/desktop-pairing/device-code')) return 'desktop_pairing_request';
  if (p.includes('/desktop-pairing/token')) return 'desktop_pairing_poll';
  if (p.includes('/desktop-pairing/verify')) return 'desktop_pairing_verify';
  if (p.includes('/desktop-pairing/approve')) return 'desktop_pairing_approve';

  // VPN, Backup, Sync
  if (p.startsWith('/api/vpn/') || p === '/api/vpn') return 'vpn_operations';
  if (p.startsWith('/api/backup/') || p === '/api/backup') return 'backup_operations';
  if (p.startsWith('/api/sync/')) return 'sync_operations';

  // Benchmark (POST run before admin catch-all)
  if (m === 'POST' && p.includes('/benchmark/run')) return 'admin_benchmark';

  // API Keys
  if (p.startsWith('/api/api-keys')) return 'api_key_operations';

  // Users
  if (p.startsWith('/api/users')) return 'user_operations';

  // System / Monitoring / Energy (GET = monitor, else admin)
  if (p.startsWith('/api/system/') || p.startsWith('/api/monitoring/') || p.startsWith('/api/energy/')) {
    return m === 'GET' ? 'system_monitor' : 'admin_operations';
  }

  // VCL
  if (p.startsWith('/api/vcl/')) return m === 'GET' ? 'file_list' : 'file_write';

  // SSD Cache
  if (p.startsWith('/api/ssd-cache/')) return m === 'GET' ? 'file_list' : 'admin_operations';

  // Admin catch-all
  const adminPrefixes = [
    '/api/admin/', '/api/admin-db/', '/api/schedulers/', '/api/fans/',
    '/api/power/', '/api/pihole/', '/api/sleep/', '/api/cloud/',
    '/api/updates/', '/api/samba/', '/api/webdav/', '/api/plugins/',
    '/api/notifications/', '/api/benchmark/', '/api/smart-devices/',
  ];
  if (adminPrefixes.some(prefix => p.startsWith(prefix))) return 'admin_operations';

  return null;
}
