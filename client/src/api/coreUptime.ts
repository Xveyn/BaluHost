/**
 * API client for Core Operating Hours (Kernbetriebszeit).
 *
 * Time windows during which the server must remain awake.
 */
import { apiClient } from '../lib/api';

export interface CoreUptimeWindow {
  id: number;
  enabled: boolean;
  label: string | null;
  start_time: string;   // "HH:MM"
  end_time: string;     // "HH:MM"
  weekdays: number[];   // 0=Mon..6=Sun, sorted, deduped
  created_at: string;
  updated_at: string;
}

export interface CoreUptimeWindowCreate {
  enabled?: boolean;
  label?: string | null;
  start_time: string;
  end_time: string;
  weekdays: number[];
}

export type CoreUptimeWindowUpdate = Partial<CoreUptimeWindowCreate>;

const BASE = '/api/system/sleep/core-uptime/windows';

export async function listCoreUptimeWindows(): Promise<CoreUptimeWindow[]> {
  const r = await apiClient.get<CoreUptimeWindow[]>(BASE);
  return r.data;
}

export async function createCoreUptimeWindow(
  data: CoreUptimeWindowCreate,
): Promise<CoreUptimeWindow> {
  const r = await apiClient.post<CoreUptimeWindow>(BASE, data);
  return r.data;
}

export async function updateCoreUptimeWindow(
  id: number,
  data: CoreUptimeWindowUpdate,
): Promise<CoreUptimeWindow> {
  const r = await apiClient.put<CoreUptimeWindow>(`${BASE}/${id}`, data);
  return r.data;
}

export async function deleteCoreUptimeWindow(id: number): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
