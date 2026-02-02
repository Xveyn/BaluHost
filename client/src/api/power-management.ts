/**
 * API client for CPU Power Management
 *
 * Controls CPU frequency scaling profiles and power demands.
 */

import { apiClient } from '../lib/api';

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
