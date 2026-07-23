/**
 * API client for the topbar status strip.
 */
import { apiClient } from '../lib/api';

/** Core pill ids plus `plugin:<name>:<suffix>` — validated server-side. */
export type PillId = string;

export type DisplayMode = 'always' | 'when_off' | 'when_on';

export type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';
export type PillKind = 'state' | 'activity' | 'alert';
export type PillVisibility = 'admin' | 'all';

export interface PillState {
  id: PillId;
  kind: PillKind;
  tone: PillTone;
  label_key: string;
  label_params?: Record<string, unknown> | null;
  value?: string | null;
  value_key?: string | null;
  value_params?: Record<string, unknown> | null;
  icon?: string | null;
  href: string;
  extra?: Record<string, unknown> | null;
  label_text?: string | null;
  translations?: Record<string, Record<string, string>> | null;
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
  icon: string;
  display_mode: DisplayMode;
  display_mode_configurable: boolean;
  name_text?: string | null;
  translations?: Record<string, Record<string, string>> | null;
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
