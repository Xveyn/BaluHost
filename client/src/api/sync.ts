/**
 * API client for sync settings: schedules, bandwidth, devices, folders.
 * Consolidates all sync-related endpoints using apiClient (Axios).
 */

import { apiClient } from '../lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SyncSchedule {
  schedule_id: number;
  device_id: string;
  device_name?: string | null;
  schedule_type: string;
  time_of_day: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  sync_deletions?: boolean;
  resolve_conflicts?: string;
  is_enabled?: boolean;
  auto_vpn?: boolean;
  created_at?: string;
}

export interface CreateScheduleRequest {
  device_id: string;
  schedule_type: string;
  time_of_day: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  sync_deletions?: boolean;
  resolve_conflicts?: string;
  auto_vpn?: boolean;
}

export interface SleepScheduleInfo {
  enabled: boolean;
  sleep_time: string;
  wake_time: string;
  mode: string;
}

export interface SyncPreflightResponse {
  sync_allowed: boolean;
  current_sleep_state: string;
  sleep_schedule: SleepScheduleInfo | null;
  next_sleep_at: string | null;
  next_wake_at: string | null;
  block_reason: string | null;
}

// ---------------------------------------------------------------------------
// Preflight (Sleep-Aware Sync)
// ---------------------------------------------------------------------------

export async function getSyncPreflight(): Promise<SyncPreflightResponse> {
  const res = await apiClient.get('/api/sync/preflight');
  return res.data;
}

// ---------------------------------------------------------------------------
// Schedules
// ---------------------------------------------------------------------------

export async function listSyncSchedules(): Promise<SyncSchedule[]> {
  const res = await apiClient.get('/api/sync/schedule/list');
  const schedules = res.data.schedules || [];
  return schedules.map((s: Record<string, unknown>) => ({
    ...s,
    is_enabled: s.is_enabled ?? s.enabled ?? true,
  })) as SyncSchedule[];
}

export async function createSyncSchedule(data: CreateScheduleRequest): Promise<SyncSchedule> {
  const res = await apiClient.post('/api/sync/schedule/create', data);
  return res.data;
}

export async function updateSyncSchedule(
  id: number,
  data: Record<string, unknown>,
): Promise<SyncSchedule> {
  const res = await apiClient.put(`/api/sync/schedule/${id}`, data);
  return res.data;
}

export async function disableSyncSchedule(id: number): Promise<void> {
  await apiClient.post(`/api/sync/schedule/${id}/disable`);
}

export async function enableSyncSchedule(id: number): Promise<void> {
  await apiClient.post(`/api/sync/schedule/${id}/enable`);
}

export async function deleteSyncSchedule(id: number): Promise<void> {
  await apiClient.delete(`/api/sync/schedule/${id}`);
}

// ---------------------------------------------------------------------------
// Bandwidth
// ---------------------------------------------------------------------------

export interface BandwidthLimits {
  upload_speed_limit: number | null;
  download_speed_limit: number | null;
}

export async function getBandwidthLimits(): Promise<BandwidthLimits> {
  const res = await apiClient.get('/api/sync/bandwidth/limit');
  return res.data;
}

export async function saveBandwidthLimits(
  upload: number | null,
  download: number | null,
): Promise<void> {
  await apiClient.post('/api/sync/bandwidth/limit', {
    upload_speed_limit: upload,
    download_speed_limit: download,
  });
}
