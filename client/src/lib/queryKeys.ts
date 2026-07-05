import type { TimeRange, DataSource } from '../api/monitoring';

/**
 * Central query-key factory for TanStack Query.
 *
 * Convention: keys are namespaced arrays `[domain, entity, kind, ...params]`.
 * Follow-up migrations add their domain here (e.g. `queryKeys.raid`, `queryKeys.shares`).
 */
export const queryKeys = {
  monitoring: {
    cpuCurrent: () => ['monitoring', 'cpu', 'current'] as const,
    cpuHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'cpu', 'history', duration, source] as const,
    memoryCurrent: () => ['monitoring', 'memory', 'current'] as const,
    memoryHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'memory', 'history', duration, source] as const,
    networkCurrent: () => ['monitoring', 'network', 'current'] as const,
    networkHistory: (duration: TimeRange, source: DataSource) =>
      ['monitoring', 'network', 'history', duration, source] as const,
    diskIoCurrent: () => ['monitoring', 'diskIo', 'current'] as const,
    diskIoHistory: (duration: TimeRange, source: DataSource, diskName?: string) =>
      ['monitoring', 'diskIo', 'history', duration, source, diskName ?? null] as const,
    processesCurrent: () => ['monitoring', 'processes', 'current'] as const,
    processesHistory: (duration: TimeRange, source: DataSource, processName?: string) =>
      ['monitoring', 'processes', 'history', duration, source, processName ?? null] as const,
  },
  system: {
    telemetry: () => ['system', 'telemetry'] as const,
    info: () => ['system', 'info'] as const,
    mode: () => ['system', 'mode'] as const,
  },
  raid: {
    /** Domain-Prefix — invalidiert Status + Disks auf einmal. */
    all: () => ['raid'] as const,
    status: () => ['raid', 'status'] as const,
    availableDisks: () => ['raid', 'available-disks'] as const,
  },
  backups: {
    list: () => ['backups', 'list'] as const,
  },
  shares: {
    /** Domain-Prefix — invalidiert alle drei shares-Reads auf einmal. */
    all: () => ['shares'] as const,
    userShares: () => ['shares', 'user-shares'] as const,
    sharedWithMe: () => ['shares', 'shared-with-me'] as const,
    statistics: () => ['shares', 'statistics'] as const,
  },
  plugins: {
    summary: () => ['plugins', 'summary'] as const,
  },
  activity: {
    /** User-scoped feed; scope ('mine'|'all') + limit are part of the key. */
    recent: (scope: 'mine' | 'all', limit: number) =>
      ['activity', 'recent', scope, limit] as const,
  },
  docs: {
    index: (lang: string) => ['docs', 'index', lang] as const,
    article: (slug: string, lang: string) => ['docs', 'article', slug, lang] as const,
  },
  services: {
    /** Domain-Prefix — invalidiert summary + debugSnapshot (Control-Mutations betreffen beide). */
    all: () => ['services'] as const,
    summary: () => ['services', 'summary'] as const,
    /** Full admin debug snapshot (services + dependencies + metrics), `/api/admin/debug`. */
    debugSnapshot: () => ['services', 'debug-snapshot'] as const,
  },
  users: {
    /** Domain-Prefix — invalidiert alle users-Reads (CRUD-Mutations). */
    all: () => ['users'] as const,
    list: (params: Record<string, string | undefined>) => ['users', 'list', params] as const,
  },
  remoteServers: {
    serverProfiles: () => ['remote-servers', 'server-profiles'] as const,
    vpnProfiles: () => ['remote-servers', 'vpn-profiles'] as const,
  },
  devices: {
    all: () => ['devices'] as const,
    list: () => ['devices', 'list'] as const,
  },
  mobile: {
    devices: () => ['mobile', 'devices'] as const,
    vpnTypes: () => ['mobile', 'vpn-types'] as const,
    deviceNotifications: (deviceId: string) => ['mobile', 'device-notifications', deviceId] as const,
    /** Registration-token status (poll-until-used); token is part of the key. */
    tokenStatus: (token: string) => ['mobile', 'token-status', token] as const,
  },
  smart: {
    status: () => ['smart', 'status'] as const,
    mode: () => ['smart', 'mode'] as const,
  },
  /** Smart plugs / Tapo devices (`api/smart-devices`), distinct from `smart` (disk health). */
  smartDevices: {
    list: () => ['smart-devices', 'list'] as const,
  },
  gpu: {
    current: () => ['gpu', 'current'] as const,
  },
  sleep: {
    status: () => ['sleep', 'status'] as const,
    fritzBox: () => ['sleep', 'fritzbox'] as const,
  },
  gpuPower: {
    /** Combined GPU-power status + config + capabilities for the power card. */
    overview: () => ['gpu-power', 'overview'] as const,
  },
  pihole: {
    /** Domain-Prefix. */
    all: () => ['pihole'] as const,
    /** Aggregate overview (status + summary + top domains/clients + history). */
    overview: () => ['pihole', 'overview'] as const,
    failoverStatus: () => ['pihole', 'failover-status'] as const,
    collectorStatus: () => ['pihole', 'collector-status'] as const,
  },
  fans: {
    status: () => ['fans', 'status'] as const,
    /** Combined fan status + permission for the fan-control page. */
    control: () => ['fans', 'control'] as const,
  },
  power: {
    status: () => ['power', 'status'] as const,
  },
  statusBar: {
    state: () => ['status-bar', 'state'] as const,
  },
  adminDb: {
    /** Domain-Prefix. */
    all: () => ['admin-db'] as const,
    stats: () => ['admin-db', 'stats'] as const,
    tables: () => ['admin-db', 'tables'] as const,
    tableData: (table: string | null, params: Record<string, unknown>) =>
      ['admin-db', 'table-data', table, params] as const,
  },
  benchmark: {
    /** Domain-Prefix — invalidiert disks/profiles/detail/progress/history auf einmal. */
    all: () => ['benchmark'] as const,
    disks: () => ['benchmark', 'disks'] as const,
    profiles: () => ['benchmark', 'profiles'] as const,
    detail: (id: number | null) => ['benchmark', 'detail', id] as const,
    progress: (id: number | null) => ['benchmark', 'progress', id] as const,
    history: (page: number, pageSize: number, diskName: string | null) =>
      ['benchmark', 'history', page, pageSize, diskName] as const,
  },
  sync: {
    schedules: () => ['sync', 'schedules'] as const,
    bandwidth: () => ['sync', 'bandwidth'] as const,
    preflight: () => ['sync', 'preflight'] as const,
  },
  schedulers: {
    /** Domain-Prefix — invalidiert list + history (Mutations betreffen beide). */
    all: () => ['schedulers'] as const,
    list: () => ['schedulers', 'list'] as const,
    history: (
      name: string | null,
      page: number,
      pageSize: number,
      statusFilter: string | null,
    ) => ['schedulers', 'history', name, page, pageSize, statusFilter] as const,
  },
} as const;
