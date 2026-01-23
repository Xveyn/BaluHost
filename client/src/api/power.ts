/**
 * API client for Tapo power monitoring
 */

import { apiClient } from '../lib/api';

// TypeScript interfaces
export interface PowerSample {
  timestamp: string;
  watts: number;
  voltage?: number;
  current?: number;
  energy_today?: number;
}

export interface PowerHistory {
  device_id: number;
  device_name: string;
  samples: PowerSample[];
  latest_sample?: PowerSample;
}

export interface PowerMonitoringResponse {
  devices: PowerHistory[];
  total_current_power: number;
  last_updated: string;
}

export interface CurrentPowerResponse {
  device_id: number;
  device_name: string;
  current_watts: number;
  voltage?: number;
  current?: number;
  energy_today?: number;
  timestamp: string;
  is_online: boolean;
}

export interface TapoDevice {
  id: number;
  name: string;
  device_type: string;
  ip_address: string;
  is_active: boolean;
  is_monitoring: boolean;
  last_connected?: string;
  last_error?: string;
  created_at: string;
  updated_at: string;
  created_by_user_id: number;
}

export interface TapoDeviceCreate {
  name: string;
  device_type?: string;
  ip_address: string;
  email: string;
  password: string;
  is_monitoring?: boolean;
}

export interface TapoDeviceUpdate {
  name?: string;
  device_type?: string;
  ip_address?: string;
  email?: string;
  password?: string;
  is_active?: boolean;
  is_monitoring?: boolean;
}

// Power Monitoring API (All authenticated users)

export async function getPowerHistory(): Promise<PowerMonitoringResponse> {
  const response = await apiClient.get<PowerMonitoringResponse>('/api/tapo/power/history');
  return response.data;
}

export async function getCurrentPower(deviceId: number): Promise<CurrentPowerResponse> {
  const response = await apiClient.get<CurrentPowerResponse>(`/api/tapo/power/current/${deviceId}`);
  return response.data;
}

// Device Configuration API (Admin only)

export async function listTapoDevices(): Promise<TapoDevice[]> {
  const response = await apiClient.get<TapoDevice[]>('/api/tapo/devices');
  return response.data;
}

export async function getTapoDevice(deviceId: number): Promise<TapoDevice> {
  const response = await apiClient.get<TapoDevice>(`/api/tapo/devices/${deviceId}`);
  return response.data;
}

export async function createTapoDevice(device: TapoDeviceCreate): Promise<TapoDevice> {
  const response = await apiClient.post<TapoDevice>('/api/tapo/devices', device);
  return response.data;
}

export async function updateTapoDevice(
  deviceId: number,
  updates: TapoDeviceUpdate
): Promise<TapoDevice> {
  const response = await apiClient.patch<TapoDevice>(`/api/tapo/devices/${deviceId}`, updates);
  return response.data;
}

export async function deleteTapoDevice(deviceId: number): Promise<void> {
  await apiClient.delete(`/api/tapo/devices/${deviceId}`);
}
