/**
 * API client for Sleep Mode
 *
 * Two-stage sleep system: Soft Sleep (reduced power, server reachable)
 * and True Suspend (systemctl suspend, WoL/rtcwake wake).
 */

import { apiClient } from '../lib/api';

// ============================================================================
// Types
// ============================================================================

export type SleepState =
  | 'awake'
  | 'entering_soft_sleep'
  | 'soft_sleep'
  | 'entering_suspend'
  | 'true_suspend'
  | 'waking';

export type SleepTrigger =
  | 'manual'
  | 'auto_idle'
  | 'schedule'
  | 'auto_wake'
  | 'auto_escalation'
  | 'wol'
  | 'rtc_wake';

export type ScheduleMode = 'soft' | 'suspend';

export interface ActivityMetrics {
  cpu_usage_avg: number;
  disk_io_avg_mbps: number;
  active_uploads: number;
  active_downloads: number;
  http_requests_per_minute: number;
}

export interface SleepStatusResponse {
  current_state: SleepState;
  state_since: string | null;
  idle_seconds: number;
  idle_threshold_seconds: number;
  activity_metrics: ActivityMetrics;
  paused_services: string[];
  spun_down_disks: string[];
  auto_idle_enabled: boolean;
  schedule_enabled: boolean;
  escalation_enabled: boolean;
}

export interface SleepConfigResponse {
  auto_idle_enabled: boolean;
  idle_timeout_minutes: number;
  idle_cpu_threshold: number;
  idle_disk_io_threshold: number;
  idle_http_threshold: number;
  auto_escalation_enabled: boolean;
  escalation_after_minutes: number;
  schedule_enabled: boolean;
  schedule_sleep_time: string;
  schedule_wake_time: string;
  schedule_mode: ScheduleMode;
  wol_mac_address: string | null;
  wol_broadcast_address: string | null;
  pause_monitoring: boolean;
  pause_disk_io: boolean;
  reduced_telemetry_interval: number;
  disk_spindown_enabled: boolean;
}

export interface SleepConfigUpdate {
  auto_idle_enabled?: boolean;
  idle_timeout_minutes?: number;
  idle_cpu_threshold?: number;
  idle_disk_io_threshold?: number;
  idle_http_threshold?: number;
  auto_escalation_enabled?: boolean;
  escalation_after_minutes?: number;
  schedule_enabled?: boolean;
  schedule_sleep_time?: string;
  schedule_wake_time?: string;
  schedule_mode?: ScheduleMode;
  wol_mac_address?: string | null;
  wol_broadcast_address?: string | null;
  pause_monitoring?: boolean;
  pause_disk_io?: boolean;
  reduced_telemetry_interval?: number;
  disk_spindown_enabled?: boolean;
}

export interface SleepCapabilities {
  hdparm_available: boolean;
  rtcwake_available: boolean;
  systemctl_available: boolean;
  can_suspend: boolean;
  wol_interfaces: string[];
  data_disk_devices: string[];
}

export interface SleepHistoryEntry {
  id: number;
  timestamp: string;
  previous_state: SleepState;
  new_state: SleepState;
  reason: string;
  triggered_by: SleepTrigger;
  details: Record<string, unknown> | null;
  duration_seconds: number | null;
}

export interface SleepHistoryResponse {
  entries: SleepHistoryEntry[];
  total: number;
}

// ============================================================================
// Display metadata
// ============================================================================

export const SLEEP_STATE_INFO: Record<SleepState, { label: string; color: string; bgColor: string }> = {
  awake: { label: 'Awake', color: 'text-emerald-400', bgColor: 'bg-emerald-500/20' },
  entering_soft_sleep: { label: 'Entering Sleep...', color: 'text-amber-400', bgColor: 'bg-amber-500/20' },
  soft_sleep: { label: 'Soft Sleep', color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
  entering_suspend: { label: 'Suspending...', color: 'text-amber-400', bgColor: 'bg-amber-500/20' },
  true_suspend: { label: 'Suspended', color: 'text-purple-400', bgColor: 'bg-purple-500/20' },
  waking: { label: 'Waking...', color: 'text-amber-400', bgColor: 'bg-amber-500/20' },
};

export const TRIGGER_LABELS: Record<SleepTrigger, string> = {
  manual: 'Manual',
  auto_idle: 'Auto Idle',
  schedule: 'Schedule',
  auto_wake: 'Auto Wake',
  auto_escalation: 'Auto Escalation',
  wol: 'Wake-on-LAN',
  rtc_wake: 'RTC Wake',
};

// ============================================================================
// API functions
// ============================================================================

export async function getSleepStatus(): Promise<SleepStatusResponse> {
  const response = await apiClient.get<SleepStatusResponse>('/api/system/sleep/status');
  return response.data;
}

export async function enterSoftSleep(reason?: string): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post<{ success: boolean; message: string }>(
    '/api/system/sleep/soft',
    { reason },
  );
  return response.data;
}

export async function exitSoftSleep(): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post<{ success: boolean; message: string }>(
    '/api/system/sleep/wake',
  );
  return response.data;
}

export async function enterSuspend(
  wake_at?: string,
  reason?: string,
): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post<{ success: boolean; message: string }>(
    '/api/system/sleep/suspend',
    { wake_at, reason },
  );
  return response.data;
}

export async function sendWol(
  mac_address?: string,
  broadcast_address?: string,
): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.post<{ success: boolean; message: string }>(
    '/api/system/sleep/wol',
    { mac_address, broadcast_address },
  );
  return response.data;
}

export async function getSleepConfig(): Promise<SleepConfigResponse> {
  const response = await apiClient.get<SleepConfigResponse>('/api/system/sleep/config');
  return response.data;
}

export async function updateSleepConfig(config: SleepConfigUpdate): Promise<SleepConfigResponse> {
  const response = await apiClient.put<SleepConfigResponse>('/api/system/sleep/config', config);
  return response.data;
}

export async function getSleepHistory(
  limit = 50,
  offset = 0,
): Promise<SleepHistoryResponse> {
  const response = await apiClient.get<SleepHistoryResponse>('/api/system/sleep/history', {
    params: { limit, offset },
  });
  return response.data;
}

export async function getSleepCapabilities(): Promise<SleepCapabilities> {
  const response = await apiClient.get<SleepCapabilities>('/api/system/sleep/capabilities');
  return response.data;
}
