/**
 * API client for Power Presets
 *
 * Manages power presets that define CPU clock speeds for each service power property.
 */

import { apiClient } from '../lib/api';

// Types
export type ServicePowerProperty = 'idle' | 'low' | 'medium' | 'surge';

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

export interface PowerPresetSummary {
  id: number;
  name: string;
  is_system_preset: boolean;
  is_active: boolean;
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
    icon: '🌱',
    description: 'Minimaler Stromverbrauch',
  },
  'Balanced': {
    name: 'Balanced',
    color: 'blue',
    icon: '⚖️',
    description: 'Ausgewogene Balance',
  },
  'Performance': {
    name: 'Performance',
    color: 'red',
    icon: '🚀',
    description: 'Maximale Leistung',
  },
};

// Property display info
export const PROPERTY_INFO: Record<ServicePowerProperty, { name: string; color: string; icon: string; description: string }> = {
  idle: {
    name: 'Idle',
    color: 'emerald',
    icon: '🌙',
    description: 'Leerlauf, Monitoring',
  },
  low: {
    name: 'Low',
    color: 'blue',
    icon: '🔋',
    description: 'CRUD, Konfiguration',
  },
  medium: {
    name: 'Medium',
    color: 'yellow',
    icon: '⚡',
    description: 'File-Ops, Sync, SMART',
  },
  surge: {
    name: 'Surge',
    color: 'red',
    icon: '🔥',
    description: 'Backup, RAID Rebuild',
  },
};

// API Functions

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
    return `${(mhz / 1000).toFixed(1)} GHz`;
  }
  return `${mhz} MHz`;
}
