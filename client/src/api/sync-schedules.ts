/**
 * API client for sync schedule management
 */

import { buildApiUrl } from '../lib/api';

export interface SyncSchedule {
  schedule_id: number;
  device_id: string;
  schedule_type: 'daily' | 'weekly' | 'monthly';
  time_of_day: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  sync_deletions: boolean;
  resolve_conflicts: 'keep_local' | 'keep_server' | 'ask';
  is_enabled: boolean;
  next_run_at?: string | null;
  created_at: string;
}

export interface CreateScheduleRequest {
  device_id: string;
  schedule_type: 'daily' | 'weekly' | 'monthly';
  time_of_day: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  sync_deletions?: boolean;
  resolve_conflicts?: 'keep_local' | 'keep_server' | 'ask';
}

/**
 * Create a new sync schedule
 */
export async function createSyncSchedule(data: CreateScheduleRequest): Promise<SyncSchedule> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl('/api/sync/schedule/create'), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to create schedule`);
  }

  return response.json();
}

/**
 * List all sync schedules for current user
 */
export async function listSyncSchedules(): Promise<SyncSchedule[]> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl('/api/sync/schedule/list'), {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to load schedules`);
  }

  const data = await response.json();
  return data.schedules || [];
}

/**
 * Disable a sync schedule
 */
export async function disableSyncSchedule(scheduleId: number): Promise<void> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl(`/api/sync/schedule/${scheduleId}/disable`), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to disable schedule`);
  }
}
