/**
 * API client for unified device management (Mobile + Desktop)
 */

import { buildApiUrl } from '../lib/api';

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
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl('/api/devices/all'), {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to load devices`);
  }

  return response.json();
}

/**
 * Update mobile device name
 */
export async function updateMobileDeviceName(deviceId: string, name: string): Promise<void> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl(`/api/devices/mobile/${deviceId}/name?name=${encodeURIComponent(name)}`), {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to update device name`);
  }
}

/**
 * Update desktop device name
 */
export async function updateDesktopDeviceName(deviceId: string, name: string): Promise<void> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl(`/api/devices/desktop/${deviceId}/name?name=${encodeURIComponent(name)}`), {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to update device name`);
  }
}

/**
 * Delete mobile device
 */
export async function deleteMobileDevice(deviceId: string): Promise<void> {
  const token = localStorage.getItem('token');

  const response = await fetch(buildApiUrl(`/api/mobile/devices/${deviceId}`), {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `HTTP ${response.status}: Failed to delete device`);
  }
}
