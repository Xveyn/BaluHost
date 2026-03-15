import { apiClient } from '../lib/api';

export interface BaluPiConfig {
  enabled: boolean;
  url: string;
  has_secret: boolean;
  secret_preview: string;
}

export interface BaluPiConfigUpdate {
  enabled?: boolean;
  url?: string;
  secret?: string;
}

export interface BaluPiTestResult {
  reachable: boolean;
  version?: string | null;
  hostname?: string | null;
  error?: string | null;
}

export interface BaluPiGenerateSecretResponse {
  secret: string;
}

export async function getBaluPiConfig(): Promise<BaluPiConfig> {
  const { data } = await apiClient.get<BaluPiConfig>('/api/admin/balupi/config');
  return data;
}

export async function updateBaluPiConfig(update: BaluPiConfigUpdate): Promise<{ changed: string[] }> {
  const { data } = await apiClient.put<{ changed: string[] }>('/api/admin/balupi/config', update);
  return data;
}

export async function testBaluPiConnection(): Promise<BaluPiTestResult> {
  const { data } = await apiClient.post<BaluPiTestResult>('/api/admin/balupi/test');
  return data;
}

export async function generateBaluPiSecret(): Promise<BaluPiGenerateSecretResponse> {
  const { data } = await apiClient.post<BaluPiGenerateSecretResponse>('/api/admin/balupi/generate-secret');
  return data;
}
