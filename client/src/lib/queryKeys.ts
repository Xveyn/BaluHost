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
  services: {
    summary: () => ['services', 'summary'] as const,
  },
} as const;
