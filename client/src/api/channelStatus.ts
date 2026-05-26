/**
 * API client for channel status (local vs remote access detection).
 *
 * Used by the Tauri-local-admin feature to gate destructive UI actions
 * based on whether the request originates from the local network or a
 * remote (VPN) connection.
 */

import { apiClient } from '../lib/api';

export interface ChannelStatusResponse {
  channel: 'local' | 'remote';
}

/**
 * Get the current request channel ("local" or "remote") as classified
 * by the backend's channel-detection middleware.
 */
export async function getChannelStatus(): Promise<ChannelStatusResponse> {
  const { data } = await apiClient.get<ChannelStatusResponse>('/api/system/channel-status');
  return data;
}
