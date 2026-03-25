/**
 * API client for mobile device management
 */

import { apiClient } from '../lib/api';

export interface MobileRegistrationToken {
  token: string;
  server_url: string;
  expires_at: string;
  qr_code: string;
  vpn_config?: string;
  vpn_fallback?: boolean;
  device_token_validity_days: number;
}

export interface MobileDevice {
  id: string;
  user_id: number;
  username?: string; // Nur für Admin sichtbar
  device_name: string;
  device_type: string;
  device_model: string | null;
  os_version: string | null;
  app_version: string | null;
  is_active: boolean;
  last_sync: string | null;
  last_seen?: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ExpirationNotification {
  id: string;
  notification_type: string;
  sent_at: string;
  success: boolean;
  error_message: string | null;
  device_expires_at: string | null;
}

export async function generateMobileToken(
  includeVpn: boolean = false,
  deviceName: string = 'Mobile Device',
  tokenValidityDays: number = 90,
  vpnType: string = 'auto'
): Promise<MobileRegistrationToken> {
  const res = await apiClient.post('/api/mobile/token/generate', null, {
    params: {
      include_vpn: includeVpn,
      device_name: deviceName,
      token_validity_days: tokenValidityDays,
      vpn_type: vpnType
    }
  });
  return res.data;
}

export async function getAvailableVpnTypes(): Promise<string[]> {
  const res = await apiClient.get('/api/vpn/available-types');
  return res.data.available_types;
}

export async function getTokenStatus(token: string): Promise<{ used: boolean }> {
  const res = await apiClient.get(`/api/mobile/token/${encodeURIComponent(token)}/status`);
  return res.data;
}

export async function getMobileDevices(): Promise<MobileDevice[]> {
  // Add cache-busting timestamp to prevent stale data
  const res = await apiClient.get('/api/mobile/devices', {
    params: { _t: Date.now() }
  });
  return res.data;
}

export async function deleteMobileDevice(deviceId: string): Promise<void> {
  await apiClient.delete(`/api/mobile/devices/${deviceId}`);
}

export async function getDeviceNotifications(deviceId: string, limit: number = 10): Promise<ExpirationNotification[]> {
  const res = await apiClient.get(`/api/mobile/devices/${deviceId}/notifications`, {
    params: { limit }
  });
  return res.data;
}
