/**
 * API client for environment configuration management
 */

import { apiClient } from '../lib/api';

export interface EnvVarResponse {
  key: string;
  value: string;
  is_sensitive: boolean;
  category: string;
  description_key: string;
  input_type: string; // text | number | boolean | secret
  default: string | null;
  file: string; // backend | client
}

export interface EnvConfigResponse {
  backend: EnvVarResponse[];
  client: EnvVarResponse[];
  categories: string[];
}

export interface EnvVarUpdate {
  key: string;
  value: string;
}

export interface EnvConfigUpdateRequest {
  file: 'backend' | 'client';
  updates: EnvVarUpdate[];
}

export interface EnvConfigUpdateResponse {
  changed: string[];
  count: number;
}

export interface EnvVarRevealResponse {
  key: string;
  value: string;
}

export async function getEnvConfig(): Promise<EnvConfigResponse> {
  const response = await apiClient.get<EnvConfigResponse>('/api/admin/env-config');
  return response.data;
}

export async function updateEnvConfig(request: EnvConfigUpdateRequest): Promise<EnvConfigUpdateResponse> {
  const response = await apiClient.put<EnvConfigUpdateResponse>('/api/admin/env-config', request);
  return response.data;
}

export async function revealEnvVar(key: string): Promise<string> {
  const response = await apiClient.get<EnvVarRevealResponse>(`/api/admin/env-config/reveal/${encodeURIComponent(key)}`);
  return response.data.value;
}
