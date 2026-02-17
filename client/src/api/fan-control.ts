/**
 * Fan control API client
 */
import { apiClient } from '../lib/api';

// Types
export const FanMode = {
  AUTO: 'auto',
  MANUAL: 'manual',
  EMERGENCY: 'emergency',
  SCHEDULED: 'scheduled'
} as const;
export type FanMode = typeof FanMode[keyof typeof FanMode];

export const CurvePreset = {
  SILENT: 'silent',
  BALANCED: 'balanced',
  PERFORMANCE: 'performance',
  CUSTOM: 'custom'
} as const;
export type CurvePreset = typeof CurvePreset[keyof typeof CurvePreset];

export interface FanCurvePoint {
  temp: number;
  pwm: number;
}

// Preset curve definitions for immediate UI use
export const CURVE_PRESETS: Record<string, FanCurvePoint[]> = {
  silent: [
    { temp: 40, pwm: 30 },
    { temp: 55, pwm: 35 },
    { temp: 70, pwm: 55 },
    { temp: 80, pwm: 75 },
    { temp: 90, pwm: 100 },
  ],
  balanced: [
    { temp: 35, pwm: 30 },
    { temp: 50, pwm: 50 },
    { temp: 70, pwm: 80 },
    { temp: 85, pwm: 100 },
  ],
  performance: [
    { temp: 30, pwm: 40 },
    { temp: 45, pwm: 60 },
    { temp: 60, pwm: 85 },
    { temp: 75, pwm: 100 },
  ],
};

export interface FanActiveSchedule {
  id: number;
  name: string;
  start_time: string; // "HH:MM"
  end_time: string;   // "HH:MM"
}

export interface FanInfo {
  fan_id: string;
  name: string;
  rpm: number | null;
  pwm_percent: number;
  temperature_celsius: number | null;
  mode: FanMode;
  is_active: boolean;
  min_pwm_percent: number;
  max_pwm_percent: number;
  emergency_temp_celsius: number;
  temp_sensor_id: string | null;
  curve_points: FanCurvePoint[];
  hysteresis_celsius: number;
  active_schedule?: FanActiveSchedule | null;
}

export interface FanStatusResponse {
  fans: FanInfo[];
  is_dev_mode: boolean;
  is_using_linux_backend: boolean;
  permission_status: string;
  backend_available: boolean;
}

export interface SetFanModeRequest {
  fan_id: string;
  mode: FanMode;
}

export interface SetFanModeResponse {
  success: boolean;
  fan_id: string;
  mode: FanMode;
  message?: string;
}

export interface SetFanPWMRequest {
  fan_id: string;
  pwm_percent: number;
}

export interface SetFanPWMResponse {
  success: boolean;
  fan_id: string;
  pwm_percent: number;
  actual_rpm: number | null;
  message?: string;
}

export interface UpdateFanCurveRequest {
  fan_id: string;
  curve_points: FanCurvePoint[];
}

export interface UpdateFanCurveResponse {
  success: boolean;
  fan_id: string;
  curve_points: FanCurvePoint[];
  message?: string;
}

export interface FanSampleData {
  timestamp: string;
  fan_id: string;
  pwm_percent: number;
  rpm: number | null;
  temperature_celsius: number | null;
  mode: string;
}

export interface FanHistoryResponse {
  samples: FanSampleData[];
  total_count: number;
  fan_id: string | null;
}

export interface SwitchBackendRequest {
  use_linux_backend: boolean;
}

export interface SwitchBackendResponse {
  success: boolean;
  is_using_linux_backend: boolean;
  backend_available: boolean;
  message?: string;
}

export interface PermissionStatusResponse {
  has_write_permission: boolean;
  status: string;
  message: string;
  suggestions: string[];
}

export interface PresetInfo {
  name: string;
  label: string;
  description: string;
  curve_points: FanCurvePoint[];
}

export interface PresetsResponse {
  presets: PresetInfo[];
}

export interface ApplyPresetRequest {
  fan_id: string;
  preset: CurvePreset;
}

export interface ApplyPresetResponse {
  success: boolean;
  fan_id: string;
  preset: string;
  curve_points: FanCurvePoint[];
  message?: string;
}

export interface UpdateFanConfigRequest {
  fan_id: string;
  hysteresis_celsius?: number;
  min_pwm_percent?: number;
  max_pwm_percent?: number;
  emergency_temp_celsius?: number;
}

export interface UpdateFanConfigResponse {
  success: boolean;
  fan_id: string;
  hysteresis_celsius: number;
  min_pwm_percent: number;
  max_pwm_percent: number;
  emergency_temp_celsius: number;
  message?: string;
}

// Schedule types
export interface FanScheduleEntry {
  id: number;
  fan_id: string;
  name: string;
  start_time: string; // "HH:MM"
  end_time: string;   // "HH:MM"
  curve_points: FanCurvePoint[];
  priority: number;
  is_enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CreateFanScheduleEntryRequest {
  name: string;
  start_time: string;
  end_time: string;
  curve_points: FanCurvePoint[];
  priority?: number;
  is_enabled?: boolean;
}

export interface UpdateFanScheduleEntryRequest {
  name?: string;
  start_time?: string;
  end_time?: string;
  curve_points?: FanCurvePoint[];
  priority?: number;
  is_enabled?: boolean;
}

export interface FanScheduleListResponse {
  entries: FanScheduleEntry[];
  fan_id: string;
  total_count: number;
}

export interface ActiveScheduleInfo {
  active_entry: FanScheduleEntry | null;
  next_entry: FanScheduleEntry | null;
  is_using_default_curve: boolean;
}

// API Functions

/**
 * Get current fan status
 */
export async function getFanStatus(): Promise<FanStatusResponse> {
  const response = await apiClient.get<FanStatusResponse>('/api/fans/status');
  return response.data;
}

/**
 * Get list of all fans
 */
export async function listFans(): Promise<FanInfo[]> {
  const response = await apiClient.get<FanInfo[]>('/api/fans/list');
  return response.data;
}

/**
 * Set fan operation mode
 */
export async function setFanMode(
  fanId: string,
  mode: FanMode
): Promise<SetFanModeResponse> {
  const request: SetFanModeRequest = { fan_id: fanId, mode };
  const response = await apiClient.post<SetFanModeResponse>('/api/fans/mode', request);
  return response.data;
}

/**
 * Set manual PWM value for a fan
 */
export async function setFanPWM(
  fanId: string,
  pwmPercent: number
): Promise<SetFanPWMResponse> {
  const request: SetFanPWMRequest = { fan_id: fanId, pwm_percent: pwmPercent };
  const response = await apiClient.post<SetFanPWMResponse>('/api/fans/pwm', request);
  return response.data;
}

/**
 * Update fan temperature curve
 */
export async function updateFanCurve(
  fanId: string,
  curvePoints: FanCurvePoint[]
): Promise<UpdateFanCurveResponse> {
  const request: UpdateFanCurveRequest = { fan_id: fanId, curve_points: curvePoints };
  const response = await apiClient.put<UpdateFanCurveResponse>('/api/fans/curve', request);
  return response.data;
}

/**
 * Get fan history
 */
export async function getFanHistory(
  fanId?: string,
  limit: number = 100,
  offset: number = 0
): Promise<FanHistoryResponse> {
  const params: Record<string, any> = { limit, offset };
  if (fanId) {
    params.fan_id = fanId;
  }

  const response = await apiClient.get<FanHistoryResponse>('/api/fans/history', { params });
  return response.data;
}

/**
 * Switch between Linux and dev backend
 */
export async function switchBackend(
  useLinuxBackend: boolean
): Promise<SwitchBackendResponse> {
  const request: SwitchBackendRequest = { use_linux_backend: useLinuxBackend };
  const response = await apiClient.post<SwitchBackendResponse>('/api/fans/backend', request);
  return response.data;
}

/**
 * Get permission status
 */
export async function getPermissionStatus(): Promise<PermissionStatusResponse> {
  const response = await apiClient.get<PermissionStatusResponse>('/api/fans/permissions');
  return response.data;
}

/**
 * Get available curve presets
 */
export async function getPresets(): Promise<PresetsResponse> {
  const response = await apiClient.get<PresetsResponse>('/api/fans/presets');
  return response.data;
}

/**
 * Apply a preset curve to a fan
 */
export async function applyPreset(
  fanId: string,
  preset: CurvePreset
): Promise<ApplyPresetResponse> {
  const request: ApplyPresetRequest = { fan_id: fanId, preset };
  const response = await apiClient.post<ApplyPresetResponse>('/api/fans/preset', request);
  return response.data;
}

/**
 * Update fan configuration (hysteresis, limits, etc.)
 */
export async function updateFanConfig(
  fanId: string,
  config: Omit<UpdateFanConfigRequest, 'fan_id'>
): Promise<UpdateFanConfigResponse> {
  const request: UpdateFanConfigRequest = { fan_id: fanId, ...config };
  const response = await apiClient.patch<UpdateFanConfigResponse>('/api/fans/config', request);
  return response.data;
}

// --- Schedule API Functions ---

/**
 * Get all schedule entries for a fan
 */
export async function getFanSchedule(fanId: string): Promise<FanScheduleListResponse> {
  const response = await apiClient.get<FanScheduleListResponse>(`/api/fans/${encodeURIComponent(fanId)}/schedule`);
  return response.data;
}

/**
 * Create a new schedule entry for a fan
 */
export async function createFanScheduleEntry(
  fanId: string,
  entry: CreateFanScheduleEntryRequest
): Promise<FanScheduleEntry> {
  const response = await apiClient.post<FanScheduleEntry>(
    `/api/fans/${encodeURIComponent(fanId)}/schedule`,
    entry
  );
  return response.data;
}

/**
 * Update an existing schedule entry
 */
export async function updateFanScheduleEntry(
  fanId: string,
  entryId: number,
  update: UpdateFanScheduleEntryRequest
): Promise<FanScheduleEntry> {
  const response = await apiClient.put<FanScheduleEntry>(
    `/api/fans/${encodeURIComponent(fanId)}/schedule/${entryId}`,
    update
  );
  return response.data;
}

/**
 * Delete a schedule entry
 */
export async function deleteFanScheduleEntry(
  fanId: string,
  entryId: number
): Promise<void> {
  await apiClient.delete(`/api/fans/${encodeURIComponent(fanId)}/schedule/${entryId}`);
}

/**
 * Get the currently active schedule entry for a fan
 */
export async function getActiveFanSchedule(fanId: string): Promise<ActiveScheduleInfo> {
  const response = await apiClient.get<ActiveScheduleInfo>(
    `/api/fans/${encodeURIComponent(fanId)}/schedule/active`
  );
  return response.data;
}
