import { apiClient } from '../lib/api';

export interface ApiKeyPublic {
  id: number;
  name: string;
  key_prefix: string;
  created_by_user_id: number;
  created_by_username: string;
  target_user_id: number;
  target_username: string;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  use_count: number;
  created_at: string;
  revoked_at: string | null;
  revocation_reason: string | null;
}

export interface ApiKeyCreated {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
  target_user_id: number;
  target_username: string;
  created_by_username: string;
  expires_at: string | null;
  created_at: string;
}

export interface CreateApiKeyPayload {
  name: string;
  target_user_id: number;
  expires_in_days: number | null;
}

export interface EligibleUser {
  id: number;
  username: string;
  role: string;
}

export async function createApiKey(payload: CreateApiKeyPayload): Promise<ApiKeyCreated> {
  const res = await apiClient.post('/api/api-keys', payload);
  return res.data;
}

export async function listApiKeys(): Promise<{ keys: ApiKeyPublic[]; total: number }> {
  const res = await apiClient.get('/api/api-keys');
  return res.data;
}

export async function getApiKey(keyId: number): Promise<ApiKeyPublic> {
  const res = await apiClient.get(`/api/api-keys/${keyId}`);
  return res.data;
}

export async function revokeApiKey(keyId: number, reason?: string): Promise<void> {
  await apiClient.delete(`/api/api-keys/${keyId}`, {
    params: reason ? { reason } : undefined,
  });
}

export async function getEligibleUsers(): Promise<EligibleUser[]> {
  const res = await apiClient.get('/api/api-keys/eligible-users');
  return res.data;
}

export function getKeyStatus(key: ApiKeyPublic): 'active' | 'revoked' | 'expired' {
  if (!key.is_active) return 'revoked';
  if (key.expires_at) {
    const exp = new Date(key.expires_at);
    if (exp <= new Date()) return 'expired';
  }
  return 'active';
}
