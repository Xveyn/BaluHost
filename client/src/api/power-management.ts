/**
 * API client for CPU Power Management
 *
 * Controls CPU frequency scaling profiles, power demands, and power presets.
 * Consolidated from power-management.ts and power-presets.ts.
 */

import { apiClient } from '../lib/api';
import { formatNumber } from '../lib/formatters';

// Power profile enum
export type PowerProfile = 'idle' | 'low' | 'medium' | 'surge';

// Service power property (same values as PowerProfile, but represents service intensity)
export type ServicePowerProperty = 'idle' | 'low' | 'medium' | 'surge';

// Preset summary for embedding in status
export interface PowerPresetSummary {
  id: number;
  name: string;
  is_system_preset: boolean;
  is_active: boolean;
}

// Response types
export interface PowerDemandInfo {
  source: string;
  level: PowerProfile;
  power_property?: ServicePowerProperty;
  registered_at: string;
  expires_at?: string;
  description?: string;
}

export interface PowerProfileConfig {
  profile: PowerProfile;
  governor: string;
  energy_performance_preference: string;
  min_freq_mhz?: number;
  max_freq_mhz?: number;
  description: string;
}

export interface PermissionStatus {
  user: string;
  groups: string[];
  in_cpufreq_group: boolean;
  sudo_available: boolean;
  files: Record<string, boolean | null>;
  errors: string[];
  has_write_access: boolean;
}

export interface PowerStatusResponse {
  current_profile: PowerProfile;
  current_property?: ServicePowerProperty;
  current_frequency_mhz?: number;
  target_frequency_range?: string;
  active_demands: PowerDemandInfo[];
  auto_scaling_enabled: boolean;
  is_dev_mode: boolean;
  is_using_linux_backend: boolean;
  linux_backend_available: boolean;
  can_switch_backend: boolean;
  permission_status?: PermissionStatus;
  last_profile_change?: string;
  cooldown_remaining_seconds?: number;
  active_preset?: PowerPresetSummary;
}

export interface PowerProfilesResponse {
  profiles: PowerProfileConfig[];
  current_profile: PowerProfile;
}

export interface SetProfileRequest {
  profile: PowerProfile;
  duration_seconds?: number;
  reason?: string;
}

export interface SetProfileResponse {
  success: boolean;
  message: string;
  previous_profile: PowerProfile;
  new_profile: PowerProfile;
  applied_at: string;
}

export interface PowerHistoryEntry {
  timestamp: string;
  profile: PowerProfile;
  reason: string;
  source?: string;
  frequency_mhz?: number;
}

export interface PowerHistoryResponse {
  entries: PowerHistoryEntry[];
  total_entries: number;
  from_timestamp?: string;
  to_timestamp?: string;
}

export interface RegisterDemandRequest {
  source: string;
  level: PowerProfile;
  timeout_seconds?: number;
  description?: string;
}

export interface RegisterDemandResponse {
  success: boolean;
  message: string;
  demand_id: string;
  resulting_profile: PowerProfile;
}

export interface UnregisterDemandRequest {
  source: string;
}

export interface UnregisterDemandResponse {
  success: boolean;
  message: string;
  resulting_profile: PowerProfile;
}

export interface AutoScalingConfig {
  enabled: boolean;
  cpu_surge_threshold: number;
  cpu_medium_threshold: number;
  cpu_low_threshold: number;
  cooldown_seconds: number;
  use_cpu_monitoring: boolean;
}

export interface AutoScalingConfigResponse {
  config: AutoScalingConfig;
  current_cpu_usage?: number;
}

// Service Intensity types
export interface ServiceIntensityInfo {
  name: string;
  display_name: string;
  intensity_level: ServicePowerProperty;
  intensity_source: 'demand' | 'service' | 'cpu_usage' | 'inferred';
  has_active_demand: boolean;
  demand_description?: string;
  demand_registered_at?: string;
  demand_expires_at?: string;
  cpu_percent?: number;
  memory_mb?: number;
  pid?: number;
  is_alive: boolean;
}

export interface ServiceIntensityResponse {
  services: ServiceIntensityInfo[];
  timestamp: string;
  total_services: number;
  active_demands_count: number;
  highest_intensity: ServicePowerProperty;
}

export interface SwitchBackendRequest {
  use_linux_backend: boolean;
}

export interface SwitchBackendResponse {
  success: boolean;
  message: string;
  is_using_linux_backend: boolean;
  previous_backend: string;
  new_backend: string;
}

// Profile display info
export const PROFILE_INFO: Record<PowerProfile, { name: string; color: string; icon: string }> = {
  idle: { name: 'Idle', color: 'green', icon: '🌙' },
  low: { name: 'Low', color: 'blue', icon: '🔋' },
  medium: { name: 'Medium', color: 'yellow', icon: '⚡' },
  surge: { name: 'Surge', color: 'red', icon: '🔥' },
};

// API Functions

/**
 * Get current power management status
 */
export async function getPowerStatus(): Promise<PowerStatusResponse> {
  const response = await apiClient.get<PowerStatusResponse>('/api/power/status');
  return response.data;
}

/**
 * Get all available power profiles
 */
export async function getPowerProfiles(): Promise<PowerProfilesResponse> {
  const response = await apiClient.get<PowerProfilesResponse>('/api/power/profiles');
  return response.data;
}

/**
 * Set power profile manually (admin only)
 */
export async function setPowerProfile(request: SetProfileRequest): Promise<SetProfileResponse> {
  const response = await apiClient.post<SetProfileResponse>('/api/power/profile', request);
  return response.data;
}

/**
 * Get active power demands
 */
export async function getPowerDemands(): Promise<PowerDemandInfo[]> {
  const response = await apiClient.get<PowerDemandInfo[]>('/api/power/demands');
  return response.data;
}

/**
 * Register a power demand (admin only)
 */
export async function registerPowerDemand(
  request: RegisterDemandRequest
): Promise<RegisterDemandResponse> {
  const response = await apiClient.post<RegisterDemandResponse>('/api/power/demands', request);
  return response.data;
}

/**
 * Unregister a power demand (admin only)
 */
export async function unregisterPowerDemand(
  request: UnregisterDemandRequest
): Promise<UnregisterDemandResponse> {
  const response = await apiClient.delete<UnregisterDemandResponse>('/api/power/demands', {
    data: request,
  });
  return response.data;
}

/**
 * Get power profile change history
 */
export async function getPowerMgmtHistory(
  limit = 100,
  offset = 0
): Promise<PowerHistoryResponse> {
  const response = await apiClient.get<PowerHistoryResponse>('/api/power/history', {
    params: { limit, offset },
  });
  return response.data;
}

/**
 * Get auto-scaling configuration
 */
export async function getAutoScalingConfig(): Promise<AutoScalingConfigResponse> {
  const response = await apiClient.get<AutoScalingConfigResponse>('/api/power/auto-scaling');
  return response.data;
}

/**
 * Update auto-scaling configuration (admin only)
 */
export async function updateAutoScalingConfig(
  config: AutoScalingConfig
): Promise<AutoScalingConfigResponse> {
  const response = await apiClient.put<AutoScalingConfigResponse>('/api/power/auto-scaling', config);
  return response.data;
}

/**
 * Switch between dev simulation and Linux cpufreq backend (admin only)
 */
export async function switchPowerBackend(
  useLinuxBackend: boolean
): Promise<SwitchBackendResponse> {
  const response = await apiClient.post<SwitchBackendResponse>('/api/power/backend', {
    use_linux_backend: useLinuxBackend,
  });
  return response.data;
}

/**
 * Get service intensity information for all tracked services and processes
 */
export async function getServiceIntensities(): Promise<ServiceIntensityResponse> {
  const response = await apiClient.get<ServiceIntensityResponse>('/api/power/intensities');
  return response.data;
}

// ============================================================================
// Power Presets (consolidated from power-presets.ts)
// ============================================================================

export interface PowerPreset {
  id: number;
  name: string;
  description?: string;
  is_system_preset: boolean;
  is_active: boolean;
  base_clock_mhz: number;
  idle_clock_mhz: number;
  low_clock_mhz: number;
  medium_clock_mhz: number;
  surge_clock_mhz: number;
  created_at: string;
  updated_at: string;
}

export interface PowerPresetListResponse {
  presets: PowerPreset[];
  active_preset?: PowerPreset;
}

export interface CreatePresetRequest {
  name: string;
  description?: string;
  base_clock_mhz?: number;
  idle_clock_mhz?: number;
  low_clock_mhz?: number;
  medium_clock_mhz?: number;
  surge_clock_mhz?: number;
}

export interface UpdatePresetRequest {
  name?: string;
  description?: string;
  base_clock_mhz?: number;
  idle_clock_mhz?: number;
  low_clock_mhz?: number;
  medium_clock_mhz?: number;
  surge_clock_mhz?: number;
}

export interface ActivatePresetResponse {
  success: boolean;
  message: string;
  previous_preset?: PowerPresetSummary;
  new_preset: PowerPresetSummary;
}

// Preset display info
export const PRESET_INFO: Record<string, { name: string; color: string; icon: string; description: string }> = {
  'Energy Saver': {
    name: 'Energy Saver',
    color: 'emerald',
    icon: '\u{1F331}',
    description: 'Minimaler Stromverbrauch',
  },
  'Balanced': {
    name: 'Balanced',
    color: 'blue',
    icon: '\u{2696}\u{FE0F}',
    description: 'Ausgewogene Balance',
  },
  'Performance': {
    name: 'Performance',
    color: 'red',
    icon: '\u{1F680}',
    description: 'Maximale Leistung',
  },
};

// Property display info
export const PROPERTY_INFO: Record<ServicePowerProperty, { name: string; color: string; icon: string; description: string }> = {
  idle: {
    name: 'Idle',
    color: 'emerald',
    icon: '\u{1F319}',
    description: 'Leerlauf, Monitoring',
  },
  low: {
    name: 'Low',
    color: 'blue',
    icon: '\u{1F50B}',
    description: 'CRUD, Konfiguration',
  },
  medium: {
    name: 'Medium',
    color: 'yellow',
    icon: '\u{26A1}',
    description: 'File-Ops, Sync, SMART',
  },
  surge: {
    name: 'Surge',
    color: 'red',
    icon: '\u{1F525}',
    description: 'Backup, RAID Rebuild',
  },
};

// Preset API Functions

/**
 * Get all power presets
 */
export async function listPresets(): Promise<PowerPresetListResponse> {
  const response = await apiClient.get<PowerPresetListResponse>('/api/power/presets/');
  return response.data;
}

/**
 * Get the currently active preset
 */
export async function getActivePreset(): Promise<PowerPreset> {
  const response = await apiClient.get<PowerPreset>('/api/power/presets/active');
  return response.data;
}

/**
 * Get a specific preset by ID
 */
export async function getPreset(presetId: number): Promise<PowerPreset> {
  const response = await apiClient.get<PowerPreset>(`/api/power/presets/${presetId}`);
  return response.data;
}

/**
 * Activate a preset (admin only)
 */
export async function activatePreset(presetId: number): Promise<ActivatePresetResponse> {
  const response = await apiClient.post<ActivatePresetResponse>(
    `/api/power/presets/${presetId}/activate`
  );
  return response.data;
}

/**
 * Create a new custom preset (admin only)
 */
export async function createPreset(data: CreatePresetRequest): Promise<PowerPreset> {
  const response = await apiClient.post<PowerPreset>('/api/power/presets/', data);
  return response.data;
}

/**
 * Update an existing preset (admin only)
 */
export async function updatePreset(
  presetId: number,
  data: UpdatePresetRequest
): Promise<PowerPreset> {
  const response = await apiClient.put<PowerPreset>(`/api/power/presets/${presetId}`, data);
  return response.data;
}

/**
 * Delete a custom preset (admin only)
 */
export async function deletePreset(presetId: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete<{ success: boolean; message: string }>(
    `/api/power/presets/${presetId}`
  );
  return response.data;
}

/**
 * Get clock speed for a property from a preset
 */
export function getClockForProperty(preset: PowerPreset, property: ServicePowerProperty): number {
  switch (property) {
    case 'idle':
      return preset.idle_clock_mhz;
    case 'low':
      return preset.low_clock_mhz;
    case 'medium':
      return preset.medium_clock_mhz;
    case 'surge':
      return preset.surge_clock_mhz;
    default:
      return preset.base_clock_mhz;
  }
}

/**
 * Format clock speed for display
 */
export function formatClockSpeed(mhz: number): string {
  if (mhz >= 1000) {
    return `${formatNumber(mhz / 1000, 1)} GHz`;
  }
  return `${mhz} MHz`;
}
