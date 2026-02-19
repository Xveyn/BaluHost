/**
 * Centralized mock API responses for E2E tests.
 * All tests share these objects to ensure consistency.
 */

// ── Users ──────────────────────────────────────────────────────────

export const MOCK_ADMIN_USER = {
  id: 1,
  username: 'admin',
  email: 'admin@baluhost.local',
  role: 'admin',
};

export const MOCK_REGULAR_USER = {
  id: 2,
  username: 'testuser',
  email: 'user@baluhost.local',
  role: 'user',
};

// ── Auth Responses ─────────────────────────────────────────────────

export const MOCK_LOGIN_SUCCESS = {
  access_token: 'fake-jwt-token-for-e2e',
  user: MOCK_ADMIN_USER,
};

export const MOCK_LOGIN_FAILURE = {
  detail: 'Invalid username or password',
};

export const MOCK_LOGIN_2FA_REQUIRED = {
  requires_2fa: true,
  pending_token: 'pending-2fa-token-abc',
};

export const MOCK_2FA_SUCCESS = {
  access_token: 'fake-jwt-after-2fa',
  user: MOCK_ADMIN_USER,
};

// ── Health & System ────────────────────────────────────────────────

export const MOCK_HEALTH = { status: 'ok' };

export const MOCK_SYSTEM_INFO = {
  cpu: {
    usage: 12.5,
    cores: 12,
    model: 'AMD Ryzen 5 5600GT',
    frequency_mhz: 3900,
    temperature_celsius: 42,
  },
  memory: {
    total: 16 * 1024 ** 3,
    used: 6.2 * 1024 ** 3,
    speed_mts: 3200,
    type: 'DDR4',
  },
  uptime: 86400,
};

export const MOCK_STORAGE_AGGREGATED = {
  used: 120 * 1024 ** 3,
  total: 500 * 1024 ** 3,
};

export const MOCK_TELEMETRY_HISTORY = {
  cpu: [],
  memory: [],
  network: [],
};

export const MOCK_SYSTEM_MODE = { dev_mode: true };

// ── SMART ──────────────────────────────────────────────────────────

export const MOCK_SMART_STATUS = {
  devices: [
    {
      name: '/dev/sda',
      model: 'MockDisk SSD 500GB',
      serial: 'MOCK-SDA-001',
      status: 'PASSED',
      state: 'OK',
      capacity_bytes: 500 * 1024 ** 3,
      used_bytes: 120 * 1024 ** 3,
      used_percent: 24,
      temperature: 35,
      raid_member_of: 'md0',
      attributes: [
        { id: 5, name: 'Reallocated_Sector_Ct', value: 100, worst: 100, raw: '0', status: 'OK' },
        { id: 194, name: 'Temperature_Celsius', value: 65, worst: 50, raw: '35', status: 'OK' },
      ],
    },
  ],
};

// ── RAID ───────────────────────────────────────────────────────────

export const MOCK_RAID_STATUS = {
  arrays: [
    {
      name: 'md0',
      level: '1',
      status: 'optimal',
      devices: [
        { name: '/dev/sda', state: 'active sync' },
        { name: '/dev/sdb', state: 'active sync' },
      ],
      size_bytes: 500 * 1024 ** 3,
      resync_progress: null,
    },
  ],
};

// ── Schedulers ─────────────────────────────────────────────────────

export const MOCK_SCHEDULERS = {
  schedulers: [
    {
      name: 'smart_short',
      display_name: 'SMART Short Test',
      description: 'Short SMART self-test',
      is_running: false,
      is_enabled: true,
      interval_seconds: 86400,
      interval_display: 'Every 24 hours',
      last_run_at: null,
      next_run_at: null,
      last_status: 'idle',
      last_error: null,
      last_duration_ms: null,
      can_run_manually: true,
      worker_healthy: true,
    },
    {
      name: 'raid_scrub',
      display_name: 'RAID Scrub',
      description: 'RAID array scrub',
      is_running: false,
      is_enabled: true,
      interval_seconds: 604800,
      interval_display: 'Every 7 days',
      last_run_at: null,
      next_run_at: null,
      last_status: 'idle',
      last_error: null,
      last_duration_ms: null,
      can_run_manually: true,
      worker_healthy: true,
    },
  ],
  total_running: 0,
  total_enabled: 2,
};

// ── Version ────────────────────────────────────────────────────────

export const MOCK_VERSION = {
  version: '1.6.1',
  build_date: '2026-02-19',
  git_commit: 'abc1234',
};

// ── Fan / Power ────────────────────────────────────────────────────

export const MOCK_FAN_STATUS = {
  fans: [],
  is_dev_mode: true,
  is_using_linux_backend: false,
  permission_status: 'ok',
  backend_available: true,
};

export const MOCK_POWER_STATUS = {
  current_profile: 'balanced',
  current_property: 'balanced',
  current_frequency_mhz: 3900,
  target_frequency_range: '1400-3900 MHz',
  active_demands: [],
  auto_scaling_enabled: true,
  is_dev_mode: true,
  is_using_linux_backend: false,
  linux_backend_available: false,
  can_switch_backend: false,
  dynamic_mode_enabled: false,
  last_profile_change: null,
};

// ── Admin Debug ────────────────────────────────────────────────────

export const MOCK_ADMIN_DEBUG = {
  timestamp: '2026-02-19T10:00:00Z',
  services: [],
  dependencies: [],
  metrics: {},
};

// ── Plugins ────────────────────────────────────────────────────────

export const MOCK_PLUGINS = { plugins: [] };
export const MOCK_PLUGINS_MANIFEST = { plugins: [] };

// ── Network / Devices / Logging / Tapo ─────────────────────────────

export const MOCK_NETWORK_CURRENT = {
  timestamp: new Date().toISOString(),
  download_mbps: 0,
  upload_mbps: 0,
  interface_type: 'ethernet',
};

export const MOCK_DEVICES_ALL = [];

export const MOCK_FILE_ACCESS_LOGS = {
  dev_mode: true,
  logs: [],
  total: 0,
};

export const MOCK_TAPO_POWER_HISTORY = {
  devices: [],
  total_current_power: 0,
  last_updated: null,
};

// ── File Manager ───────────────────────────────────────────────────

export const MOCK_MOUNTPOINTS = {
  mountpoints: [
    {
      path: '/mnt/storage',
      name: 'Primary Storage',
      is_default: true,
      total_bytes: 500 * 1024 ** 3,
      used_bytes: 120 * 1024 ** 3,
      available_bytes: 380 * 1024 ** 3,
    },
  ],
};

export const MOCK_FILE_LIST = {
  files: [
    { name: 'Documents', path: 'Documents', type: 'directory', size: 0, modified_at: '2026-02-01T12:00:00Z', owner_id: 1 },
    { name: 'Photos', path: 'Photos', type: 'directory', size: 0, modified_at: '2026-02-10T08:00:00Z', owner_id: 1 },
    { name: 'readme.txt', path: 'readme.txt', type: 'file', size: 1024, modified_at: '2026-02-15T10:30:00Z', owner_id: 1 },
  ],
};

export const MOCK_FILE_LIST_DOCUMENTS = {
  files: [
    { name: 'report.pdf', path: 'Documents/report.pdf', type: 'file', size: 204800, modified_at: '2026-02-01T12:00:00Z', owner_id: 1 },
    { name: 'notes.md', path: 'Documents/notes.md', type: 'file', size: 512, modified_at: '2026-02-05T09:00:00Z', owner_id: 1 },
  ],
};

export const MOCK_USERS_LIST = [
  { id: 1, username: 'admin', role: 'admin' },
  { id: 2, username: 'testuser', role: 'user' },
];

export const MOCK_SMART_MODE = {
  mode: 'active',
  message: 'SMART active',
};

export const MOCK_VCL_QUOTA = {
  used_bytes: 0,
  limit_bytes: 1024 * 1024 * 100,
};
