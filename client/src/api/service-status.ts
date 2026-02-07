/**
 * Service status API client for admin debugging dashboard
 */
import { apiClient } from '../lib/api';
import { formatBytes as sharedFormatBytes } from '../lib/formatters';

// Enums
export const ServiceState = {
  RUNNING: 'running',
  STOPPED: 'stopped',
  ERROR: 'error',
  DISABLED: 'disabled'
} as const;
export type ServiceState = typeof ServiceState[keyof typeof ServiceState];

// Types
export interface ServiceStatus {
  name: string;
  display_name: string;
  state: ServiceState;
  started_at: string | null;
  uptime_seconds: number | null;
  sample_count: number | null;
  error_count: number;
  last_error: string | null;
  last_error_at: string | null;
  config_enabled: boolean;
  interval_seconds: number | null;
  restartable: boolean;
}

export interface DependencyStatus {
  name: string;
  available: boolean;
  path: string | null;
  version: string | null;
  required_for: string[];
}

export interface DbPoolStatus {
  pool_size: number;
  checked_in: number;
  checked_out: number;
  overflow: number;
}

export interface CacheStats {
  name: string;
  hits: number;
  misses: number;
  size: number;
  max_size: number | null;
}

export interface ApplicationMetrics {
  server_uptime_seconds: number;
  error_count_4xx: number;
  error_count_5xx: number;
  active_tasks: number;
  memory_bytes: number;
  memory_percent: number;
  db_pool_status: DbPoolStatus | null;
  cache_stats: CacheStats[];
}

export interface AdminDebugSnapshot {
  timestamp: string;
  services: ServiceStatus[];
  dependencies: DependencyStatus[];
  metrics: ApplicationMetrics;
}

export interface ServiceRestartRequest {
  force?: boolean;
}

export interface ServiceRestartResponse {
  success: boolean;
  service_name: string;
  previous_state: ServiceState;
  current_state: ServiceState;
  message: string | null;
}

export interface ServiceStopRequest {
  force?: boolean;
}

export interface ServiceStopResponse {
  success: boolean;
  service_name: string;
  previous_state: ServiceState;
  current_state: ServiceState;
  message: string | null;
}

export interface ServiceStartRequest {
  force?: boolean;
}

export interface ServiceStartResponse {
  success: boolean;
  service_name: string;
  previous_state: ServiceState;
  current_state: ServiceState;
  message: string | null;
}

// API Functions

/**
 * Get status for all registered services (admin only)
 */
export async function getAllServices(): Promise<ServiceStatus[]> {
  const response = await apiClient.get<ServiceStatus[]>('/api/admin/services');
  return response.data;
}

/**
 * Get status for a specific service (admin only)
 */
export async function getService(serviceName: string): Promise<ServiceStatus> {
  const response = await apiClient.get<ServiceStatus>(`/api/admin/services/${serviceName}`);
  return response.data;
}

/**
 * Restart a specific service (admin only)
 */
export async function restartService(
  serviceName: string,
  force: boolean = false
): Promise<ServiceRestartResponse> {
  const request: ServiceRestartRequest = { force };
  const response = await apiClient.post<ServiceRestartResponse>(
    `/api/admin/services/${serviceName}/restart`,
    request
  );
  return response.data;
}

/**
 * Stop a specific service (admin only)
 */
export async function stopService(
  serviceName: string,
  force: boolean = false
): Promise<ServiceStopResponse> {
  const request: ServiceStopRequest = { force };
  const response = await apiClient.post<ServiceStopResponse>(
    `/api/admin/services/${serviceName}/stop`,
    request
  );
  return response.data;
}

/**
 * Start a specific service (admin only)
 */
export async function startService(
  serviceName: string,
  force: boolean = false
): Promise<ServiceStartResponse> {
  const request: ServiceStartRequest = { force };
  const response = await apiClient.post<ServiceStartResponse>(
    `/api/admin/services/${serviceName}/start`,
    request
  );
  return response.data;
}

/**
 * Get system dependency availability (admin only)
 */
export async function getDependencies(): Promise<DependencyStatus[]> {
  const response = await apiClient.get<DependencyStatus[]>('/api/admin/dependencies');
  return response.data;
}

/**
 * Get application-level metrics (admin only)
 */
export async function getApplicationMetrics(): Promise<ApplicationMetrics> {
  const response = await apiClient.get<ApplicationMetrics>('/api/admin/metrics');
  return response.data;
}

/**
 * Get combined debug snapshot (admin only)
 */
export async function getDebugSnapshot(): Promise<AdminDebugSnapshot> {
  const response = await apiClient.get<AdminDebugSnapshot>('/api/admin/debug');
  return response.data;
}

// Helper functions

/**
 * Format uptime to human-readable string
 */
export function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-';

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (days > 0) {
    return `${days}d ${hours}h ${minutes}m`;
  } else if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

/**
 * Format bytes to human-readable string (re-export from shared formatters)
 */
export const formatBytes = sharedFormatBytes;

/**
 * Get state color for UI display
 */
export function getStateColor(state: ServiceState): string {
  switch (state) {
    case ServiceState.RUNNING:
      return 'text-green-500';
    case ServiceState.STOPPED:
      return 'text-gray-500';
    case ServiceState.ERROR:
      return 'text-red-500';
    case ServiceState.DISABLED:
      return 'text-yellow-500';
    default:
      return 'text-gray-500';
  }
}

/**
 * Get state background color for badges
 */
export function getStateBgColor(state: ServiceState): string {
  switch (state) {
    case ServiceState.RUNNING:
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    case ServiceState.STOPPED:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
    case ServiceState.ERROR:
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    case ServiceState.DISABLED:
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  }
}
