/**
 * API client for unified device management (Mobile + Desktop)
 */

import { apiClient } from '../lib/api';

export interface Device {
  id: string;
  name: string;
  type: 'mobile' | 'desktop';
  platform: string;
  model?: string | null;
  os_version?: string | null;
  app_version?: string | null;
  user_id: number;
  username?: string | null;
  last_seen?: string | null;
  last_sync?: string | null;
  created_at: string;
  is_active: boolean;
  expires_at?: string | null;
}

/**
 * Get all devices (Mobile + Desktop) for the current user.
 * Admins see all devices from all users.
 */
export async function getAllDevices(): Promise<Device[]> {
  const { data } = await apiClient.get<Device[]>('/api/devices/all');
  return data;
}

/**
 * Update mobile device name
 */
export async function updateMobileDeviceName(deviceId: string, name: string): Promise<void> {
  await apiClient.patch(`/api/devices/mobile/${deviceId}/name`, null, {
    params: { name },
  });
}

/**
 * Update desktop device name
 */
export async function updateDesktopDeviceName(deviceId: string, name: string): Promise<void> {
  await apiClient.patch(`/api/devices/desktop/${deviceId}/name`, null, {
    params: { name },
  });
}

/**
 * Delete mobile device
 */
export async function deleteMobileDevice(deviceId: string): Promise<void> {
  await apiClient.delete(`/api/mobile/devices/${deviceId}`);
}
