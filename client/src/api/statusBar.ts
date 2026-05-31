/**
 * API client for the topbar status strip.
 */
import { apiClient } from '../lib/api';

export type PillId =
  | 'power' | 'pihole' | 'uploads' | 'sync' | 'raid' | 'sleep' | 'vpn' | 'temp'
  | 'always_awake' | 'scheduler' | 'backup' | 'desktop';

export type DisplayMode = 'always' | 'when_off' | 'when_on';

export type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';
export type PillKind = 'state' | 'activity' | 'alert';
export type PillVisibility = 'admin' | 'all';

export interface PillState {
  id: PillId;
  kind: PillKind;
  tone: PillTone;
  label: string;
  value?: string | null;
  icon?: string | null;
  href: string;
  extra?: Record<string, unknown> | null;
}

export interface StatusBarStateResponse {
  pills: PillState[];
  show_bottom_upload: boolean;
}

export interface PillCatalogEntry {
  pill_id: PillId;
  name_key: string;
  enabled: boolean;
  visibility: PillVisibility;
  visibility_locked: boolean;
  sort_order: number;
  href: string;
  display_mode: DisplayMode;
  display_mode_configurable: boolean;
}

export interface StatusBarConfigResponse {
  pills: PillCatalogEntry[];
  show_bottom_upload: boolean;
}

export interface PillConfigItem {
  pill_id: PillId;
  enabled: boolean;
  visibility: PillVisibility;
  sort_order: number;
  display_mode: DisplayMode;
}

export interface StatusBarConfigUpdate {
  pills: PillConfigItem[];
  show_bottom_upload: boolean;
}

const STATE = '/api/system/statusbar/state';
const CONFIG = '/api/system/statusbar/config';

export async function getStatusBarState(): Promise<StatusBarStateResponse> {
  const r = await apiClient.get<StatusBarStateResponse>(STATE);
  return r.data;
}

export async function getStatusBarConfig(): Promise<StatusBarConfigResponse> {
  const r = await apiClient.get<StatusBarConfigResponse>(CONFIG);
  return r.data;
}

export async function updateStatusBarConfig(
  payload: StatusBarConfigUpdate,
): Promise<StatusBarConfigResponse> {
  const r = await apiClient.put<StatusBarConfigResponse>(CONFIG, payload);
  return r.data;
}
