import { apiClient } from '../lib/api';

export interface TwoFactorStatus {
  enabled: boolean;
  enabled_at: string | null;
  backup_codes_remaining: number;
}

export interface TwoFactorSetupData {
  qr_code: string;
  provisioning_uri: string;
  secret: string;
}

export interface TwoFactorBackupCodes {
  backup_codes: string[];
}

export async function get2FAStatus(): Promise<TwoFactorStatus> {
  const res = await apiClient.get('/api/auth/2fa/status');
  return res.data;
}

export async function setup2FA(): Promise<TwoFactorSetupData> {
  const res = await apiClient.post('/api/auth/2fa/setup');
  return res.data;
}

export async function verifySetup2FA(secret: string, code: string): Promise<TwoFactorBackupCodes> {
  const res = await apiClient.post('/api/auth/2fa/verify-setup', { secret, code });
  return res.data;
}

export async function disable2FA(password: string, code: string): Promise<void> {
  await apiClient.post('/api/auth/2fa/disable', { password, code });
}

export async function regenerateBackupCodes(): Promise<TwoFactorBackupCodes> {
  const res = await apiClient.post('/api/auth/2fa/backup-codes');
  return res.data;
}
