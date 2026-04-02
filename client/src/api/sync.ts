/**
 * API client for sync settings: schedules, bandwidth, devices, folders.
 * Consolidates all sync-related endpoints using apiClient (Axios).
 */

import { apiClient } from '../lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SyncDevice {
  device_id: string;
  device_name: string;
  status: string;
  last_sync: string | null;
  pending_changes: number;
  conflicts: number;
  vpn_client_id?: number | null;
  vpn_assigned_ip?: string | null;
  vpn_last_handshake?: string | null;
  vpn_active?: boolean | null;
}

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

export interface SyncFolderItem {
  id: string;
  device_id: string;
  local_path: string;
  remote_path: string;
  sync_type: string;
  auto_sync: boolean;
  last_sync?: string | null;
  status?: string | null;
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

// ---------------------------------------------------------------------------
// Devices & Folders
// ---------------------------------------------------------------------------

function mapSyncDevice(d: Record<string, unknown>): SyncDevice {
  return {
    device_id: (d.device_id ?? d.id ?? d.name) as string,
    device_name: (d.device_name ?? d.name) as string,
    status: (d.status as string) ?? 'unknown',
    last_sync: (d.last_sync ?? d.last_seen ?? null) as string | null,
    pending_changes: (d.pending_changes as number) ?? 0,
    conflicts: (d.conflicts as number) ?? 0,
    vpn_client_id: (d.vpn_client_id ?? (d.vpn as Record<string, unknown> | undefined)?.id ?? null) as number | null,
    vpn_assigned_ip: (d.vpn_assigned_ip ?? (d.vpn as Record<string, unknown> | undefined)?.assigned_ip ?? null) as string | null,
    vpn_last_handshake: (d.vpn_last_handshake ?? (d.vpn as Record<string, unknown> | undefined)?.last_handshake ?? null) as string | null,
    vpn_active: (d.vpn_active ?? (d.vpn as Record<string, unknown> | undefined)?.is_active ?? null) as boolean | null,
  };
}

function mapMobileDevice(d: Record<string, unknown>): SyncDevice {
  return {
    device_id: (d.id ?? d.device_id ?? d.deviceId) as string,
    device_name: (d.device_name ?? d.name ?? d.deviceName) as string,
    status: d.is_active === false ? 'inactive' : 'active',
    last_sync: (d.last_sync ?? d.last_seen ?? null) as string | null,
    pending_changes: (d.pending_uploads ?? d.pending_changes ?? 0) as number,
    conflicts: 0,
    vpn_client_id: (d.vpn_client_id ?? null) as number | null,
    vpn_assigned_ip: (d.vpn_assigned_ip ?? null) as string | null,
    vpn_last_handshake: (d.vpn_last_handshake ?? null) as string | null,
    vpn_active: (d.vpn_active ?? null) as boolean | null,
  };
}

export async function getSyncDevices(): Promise<SyncDevice[]> {
  // Try sync devices (desktop clients) first
  try {
    const res = await apiClient.get('/api/sync/devices');
    const list = Array.isArray(res.data) ? res.data : (res.data.devices || []);
    if (list.length > 0) return list.map(mapSyncDevice);
  } catch {
    // Non-critical
  }

  // Fallback: mobile devices endpoint
  try {
    const res = await apiClient.get('/api/mobile/devices');
    const list = Array.isArray(res.data) ? res.data : (res.data.devices || res.data);
    return list.map(mapMobileDevice);
  } catch {
    return [];
  }
}

export async function getDeviceFolders(
  deviceId: string,
): Promise<SyncFolderItem[]> {
  try {
    const res = await apiClient.get(
      `/api/mobile/sync/folders/${encodeURIComponent(deviceId)}`,
    );
    const list = Array.isArray(res.data) ? res.data : (res.data.folders || res.data);
    return list.map((f: Record<string, unknown>) => ({
      id: f.id as string,
      device_id: f.device_id as string,
      local_path: f.local_path as string,
      remote_path: f.remote_path as string,
      sync_type: f.sync_type as string,
      auto_sync: f.auto_sync as boolean,
      last_sync: (f.last_sync ?? null) as string | null,
      status: (f.status ?? null) as string | null,
    }));
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// VPN
// ---------------------------------------------------------------------------

export async function revokeVpnClient(clientId: number): Promise<void> {
  await apiClient.post(`/api/vpn/clients/${clientId}/revoke`);
}
