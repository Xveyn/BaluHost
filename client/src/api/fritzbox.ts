/**
 * API client for Fritz!Box TR-064 WoL integration.
 */

import { apiClient } from '../lib/api';

export interface FritzBoxConfig {
  host: string;
  port: number;
  username: string;
  nas_mac_address: string | null;
  enabled: boolean;
  has_password: boolean;
}

export interface FritzBoxConfigUpdate {
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  nas_mac_address?: string;
  enabled?: boolean;
}

export interface FritzBoxTestResponse {
  success: boolean;
  message: string;
}

export interface FritzBoxWolResponse {
  success: boolean;
  message: string;
}

export async function getFritzBoxConfig(): Promise<FritzBoxConfig> {
  const response = await apiClient.get<FritzBoxConfig>('/api/fritzbox/config');
  return response.data;
}

export async function updateFritzBoxConfig(config: FritzBoxConfigUpdate): Promise<FritzBoxConfig> {
  const response = await apiClient.put<FritzBoxConfig>('/api/fritzbox/config', config);
  return response.data;
}

export async function testFritzBoxConnection(): Promise<FritzBoxTestResponse> {
  const response = await apiClient.post<FritzBoxTestResponse>('/api/fritzbox/test');
  return response.data;
}

export async function sendFritzBoxWol(): Promise<FritzBoxWolResponse> {
  const response = await apiClient.post<FritzBoxWolResponse>('/api/fritzbox/wol');
  return response.data;
}
