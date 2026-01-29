/**
 * Scheduler API client for the BaluHost Scheduler Dashboard
 */
import { apiClient } from '../lib/api';

// Status constants
export const SchedulerExecStatus = {
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled'
} as const;
export type SchedulerExecStatus = typeof SchedulerExecStatus[keyof typeof SchedulerExecStatus];

export const TriggerType = {
  SCHEDULED: 'scheduled',
  MANUAL: 'manual'
} as const;
export type TriggerType = typeof TriggerType[keyof typeof TriggerType];

// Types
export interface SchedulerStatus {
  name: string;
  display_name: string;
  description: string;
  is_running: boolean;
  is_enabled: boolean;
  interval_seconds: number;
  interval_display: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: SchedulerExecStatus | null;
  last_error: string | null;
  last_duration_ms: number | null;
  config_key: string | null;
  can_run_manually: boolean;
}

export interface SchedulerListResponse {
  schedulers: SchedulerStatus[];
  total_running: number;
  total_enabled: number;
}

export interface SchedulerExecution {
  id: number;
  scheduler_name: string;
  job_id: string | null;
  started_at: string;
  completed_at: string | null;
  status: SchedulerExecStatus;
  trigger_type: TriggerType;
  result_summary: string | null;
  error_message: string | null;
  user_id: number | null;
  duration_ms: number | null;
  duration_display: string | null;
}

export interface SchedulerHistoryResponse {
  executions: SchedulerExecution[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RunNowResponse {
  success: boolean;
  message: string;
  execution_id: number | null;
  scheduler_name: string;
  status: 'started' | 'already_running' | 'disabled' | 'error';
}

export interface SchedulerToggleResponse {
  success: boolean;
  scheduler_name: string;
  is_enabled: boolean;
  message: string;
}

export interface SchedulerConfigUpdate {
  interval_seconds?: number;
  is_enabled?: boolean;
}

// API Functions

/**
 * Get status for all schedulers (admin only)
 */
export async function getSchedulers(): Promise<SchedulerListResponse> {
  const response = await apiClient.get<SchedulerListResponse>('/api/schedulers');
  return response.data;
}

/**
 * Get status for a specific scheduler (admin only)
 */
export async function getScheduler(name: string): Promise<SchedulerStatus> {
  const response = await apiClient.get<SchedulerStatus>(`/api/schedulers/${name}`);
  return response.data;
}

/**
 * Trigger a scheduler to run immediately (admin only)
 */
export async function runSchedulerNow(name: string, force: boolean = false): Promise<RunNowResponse> {
  const response = await apiClient.post<RunNowResponse>(
    `/api/schedulers/${name}/run-now`,
    { force }
  );
  return response.data;
}

/**
 * Get execution history for a specific scheduler (admin only)
 */
export async function getSchedulerHistory(
  name: string,
  page: number = 1,
  pageSize: number = 20,
  statusFilter?: SchedulerExecStatus
): Promise<SchedulerHistoryResponse> {
  const params: Record<string, any> = { page, page_size: pageSize };
  if (statusFilter) {
    params.status_filter = statusFilter;
  }
  const response = await apiClient.get<SchedulerHistoryResponse>(
    `/api/schedulers/${name}/history`,
    { params }
  );
  return response.data;
}

/**
 * Get execution history for all schedulers (admin only)
 */
export async function getAllSchedulerHistory(
  page: number = 1,
  pageSize: number = 20,
  statusFilter?: SchedulerExecStatus,
  schedulerFilter?: string
): Promise<SchedulerHistoryResponse> {
  const params: Record<string, any> = { page, page_size: pageSize };
  if (statusFilter) {
    params.status_filter = statusFilter;
  }
  if (schedulerFilter) {
    params.scheduler_filter = schedulerFilter;
  }
  const response = await apiClient.get<SchedulerHistoryResponse>(
    '/api/schedulers/history/all',
    { params }
  );
  return response.data;
}

/**
 * Update scheduler configuration (admin only)
 */
export async function updateSchedulerConfig(
  name: string,
  config: SchedulerConfigUpdate
): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.put<{ success: boolean; message: string }>(
    `/api/schedulers/${name}/config`,
    config
  );
  return response.data;
}

/**
 * Enable or disable a scheduler (admin only)
 */
export async function toggleScheduler(
  name: string,
  enabled: boolean
): Promise<SchedulerToggleResponse> {
  const response = await apiClient.post<SchedulerToggleResponse>(
    `/api/schedulers/${name}/toggle`,
    { enabled }
  );
  return response.data;
}

// Helper functions

/**
 * Format duration from milliseconds to human-readable string
 */
export function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-';

  if (ms < 1000) {
    return `${ms}ms`;
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  } else if (ms < 3600000) {
    return `${(ms / 60000).toFixed(1)}min`;
  } else {
    return `${(ms / 3600000).toFixed(1)}h`;
  }
}

/**
 * Format interval from seconds to human-readable string
 */
export function formatInterval(seconds: number): string {
  if (seconds < 60) {
    return `Every ${seconds}s`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return minutes === 1 ? 'Every minute' : `Every ${minutes} min`;
  } else if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return hours === 1 ? 'Every hour' : `Every ${hours}h`;
  } else {
    const days = Math.floor(seconds / 86400);
    return days === 1 ? 'Daily' : `Every ${days} days`;
  }
}

/**
 * Format relative time from ISO date string
 */
export function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return '-';

  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 0) {
    // Future date
    const futureSeconds = Math.abs(diffSeconds);
    const futureMinutes = Math.floor(futureSeconds / 60);
    const futureHours = Math.floor(futureMinutes / 60);
    const futureDays = Math.floor(futureHours / 24);

    if (futureDays > 0) return `in ${futureDays}d`;
    if (futureHours > 0) return `in ${futureHours}h`;
    if (futureMinutes > 0) return `in ${futureMinutes}m`;
    return 'now';
  }

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  if (diffMinutes > 0) return `${diffMinutes}m ago`;
  return 'just now';
}

/**
 * Get status color class for UI display
 */
export function getStatusColor(status: SchedulerExecStatus | null): string {
  switch (status) {
    case SchedulerExecStatus.RUNNING:
      return 'text-blue-500';
    case SchedulerExecStatus.COMPLETED:
      return 'text-green-500';
    case SchedulerExecStatus.FAILED:
      return 'text-red-500';
    case SchedulerExecStatus.CANCELLED:
      return 'text-yellow-500';
    default:
      return 'text-gray-500';
  }
}

/**
 * Get status badge classes for UI display
 */
export function getStatusBadgeClasses(status: SchedulerExecStatus | null): string {
  switch (status) {
    case SchedulerExecStatus.RUNNING:
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    case SchedulerExecStatus.COMPLETED:
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    case SchedulerExecStatus.FAILED:
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    case SchedulerExecStatus.CANCELLED:
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  }
}

/**
 * Get scheduler icon by name
 */
export function getSchedulerIcon(name: string): string {
  switch (name) {
    case 'raid_scrub':
      return '💾';
    case 'smart_scan':
      return '🔍';
    case 'backup':
      return '📦';
    case 'sync_check':
      return '🔄';
    case 'notification_check':
      return '🔔';
    case 'upload_cleanup':
      return '🧹';
    default:
      return '⏰';
  }
}

/**
 * Parse result summary JSON safely
 */
export function parseResultSummary(summary: string | null): Record<string, any> | null {
  if (!summary) return null;
  try {
    return JSON.parse(summary);
  } catch {
    return null;
  }
}
