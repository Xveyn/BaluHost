import { apiClient } from '../lib/api';

export interface SmartAttribute {
  id: number;
  name: string;
  value: number;
  worst: number;
  threshold: number;
  raw: string;
  status: string;
}

export interface SmartSelfTest {
  test_type: string;
  status: string;
  passed: boolean;
  power_on_hours: number;
}

export interface SmartDevice {
  name: string;
  model: string;
  serial: string;
  temperature: number | null;
  status: string;
  capacity_bytes: number | null;
  used_bytes: number | null;
  used_percent: number | null;
  mount_point: string | null;
  raid_member_of: string | null;
  last_self_test: SmartSelfTest | null;
  attributes: SmartAttribute[];
}

export interface SmartStatusResponse {
  checked_at: string;
  devices: SmartDevice[];
}

export async function fetchSmartStatus(): Promise<SmartStatusResponse> {
  const { data } = await apiClient.get<SmartStatusResponse>('/api/system/smart/status');
  return data;
}

export interface SmartModeResponse {
  mode: string;
  message?: string;
}

export async function getSmartMode(): Promise<SmartModeResponse> {
  const { data } = await apiClient.get<SmartModeResponse>('/api/system/smart/mode');
  return data;
}

export async function toggleSmartMode(): Promise<SmartModeResponse> {
  const { data } = await apiClient.post<SmartModeResponse>('/api/system/smart/toggle-mode');
  return data;
}

export interface SmartTestPayload {
  device?: string;
  type?: string;
}

export async function runSmartTest(payload: SmartTestPayload = {}): Promise<{ message: string }> {
  const { data } = await apiClient.post<{ message: string }>('/api/system/smart/test', payload);
  return data;
}
