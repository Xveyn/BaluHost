/** PIN login + management + admin auth-policy API client. */
import { apiClient, buildApiUrl } from '../lib/api';
import type { User } from '../types/auth';

export interface PinStatus {
  pin_enabled: boolean;
}

export interface AuthPolicy {
  pin_login_enabled: boolean;
  pin_grace_window_seconds: number;
}

/** Either a finished login (access_token) or a 2FA challenge (pending_token). */
export interface PinLoginResult {
  access_token?: string;
  user?: User;
  requires_2fa?: boolean;
  pending_token?: string;
  detail?: string;
}

/** PIN login is pre-auth and local-channel only — mirror Login.tsx's fetch path. */
export async function loginWithPin(username: string, pin: string): Promise<PinLoginResult> {
  const res = await fetch(buildApiUrl('/api/auth/login-pin'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, pin }),
  });
  const data = (await res.json().catch(() => ({}))) as PinLoginResult;
  if (!res.ok) {
    throw new Error(String(data.detail || `PIN login failed (${res.status})`));
  }
  return data;
}

export async function getPinStatus(): Promise<PinStatus> {
  const res = await apiClient.get<PinStatus>('/api/auth/pin');
  return res.data;
}

export async function setPin(pin: string, code: string): Promise<void> {
  await apiClient.post('/api/auth/pin', { pin, code });
}

export async function removePin(code: string): Promise<void> {
  await apiClient.delete('/api/auth/pin', { data: { code } });
}

export async function getAuthPolicy(): Promise<AuthPolicy> {
  const res = await apiClient.get<AuthPolicy>('/api/admin/auth-policy');
  return res.data;
}

export async function updateAuthPolicy(body: Partial<AuthPolicy>): Promise<AuthPolicy> {
  const res = await apiClient.put<AuthPolicy>('/api/admin/auth-policy', body);
  return res.data;
}
