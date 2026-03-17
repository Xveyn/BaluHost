/**
 * API client for Smart Device management (IoT / plugin-backed devices)
 */

import { apiClient } from '../lib/api';

// --- Types ---

export interface SmartDevice {
  id: number;
  name: string;
  plugin_name: string;
  device_type_id: string;
  address: string;
  mac_address: string | null;
  capabilities: string[];
  is_active: boolean;
  is_online: boolean;
  last_seen: string | null;
  last_error: string | null;
  state: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SmartDeviceListResponse {
  devices: SmartDevice[];
  total: number;
}

export interface DeviceType {
  type_id: string;
  display_name: string;
  manufacturer: string;
  capabilities: string[];
  config_schema: Record<string, unknown> | null;
  icon: string;
  plugin_name: string;
}

export interface DeviceCommand {
  capability: string;
  command: string;
  params: Record<string, unknown>;
}

export interface CommandResponse {
  success: boolean;
  state: Record<string, unknown> | null;
  error: string | null;
}

export interface PowerSummary {
  total_watts: number;
  device_count: number;
  devices: Array<{ device_id: number; name: string; watts: number }>;
}

export interface CreateDeviceRequest {
  name: string;
  plugin_name: string;
  device_type_id: string;
  address: string;
  mac_address?: string;
  config: Record<string, unknown>;
}

export interface UpdateDeviceRequest {
  name?: string;
  address?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
}

export interface HistoryEntry {
  timestamp: string;
  capability: string;
  value: unknown;
}

// --- API Functions ---

export const smartDevicesApi = {
  list: () =>
    apiClient.get<SmartDeviceListResponse>('/api/smart-devices/'),

  get: (id: number) =>
    apiClient.get<SmartDevice>(`/api/smart-devices/${id}`),

  create: (data: CreateDeviceRequest) =>
    apiClient.post<SmartDevice>('/api/smart-devices/', data),

  update: (id: number, data: UpdateDeviceRequest) =>
    apiClient.patch<SmartDevice>(`/api/smart-devices/${id}`, data),

  delete: (id: number) =>
    apiClient.delete(`/api/smart-devices/${id}`),

  command: (id: number, cmd: DeviceCommand) =>
    apiClient.post<CommandResponse>(`/api/smart-devices/${id}/command`, cmd),

  getTypes: () =>
    apiClient.get<DeviceType[]>('/api/smart-devices/types'),

  getPowerSummary: () =>
    apiClient.get<PowerSummary>('/api/smart-devices/power/summary'),

  discover: (pluginName: string) =>
    apiClient.get(`/api/smart-devices/discover/${pluginName}`),

  getHistory: (id: number, capability?: string, hours?: number) =>
    apiClient.get<HistoryEntry[]>(`/api/smart-devices/${id}/history`, {
      params: { capability, hours },
    }),
};
