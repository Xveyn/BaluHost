/** Password recovery codes: self-service management + LAN-only reset. */
import { apiClient, buildApiUrl } from '../lib/api';

export interface RecoveryCodes { recovery_codes: string[]; }
export interface RecoveryCodesStatus { configured: boolean; remaining: number; }
export interface RecoveryCodesStepUp { code?: string; current_password?: string; }

export async function generateRecoveryCodes(stepUp: RecoveryCodesStepUp): Promise<RecoveryCodes> {
  const res = await apiClient.post<RecoveryCodes>('/api/auth/recovery-codes', stepUp);
  return res.data;
}

export async function getRecoveryCodesStatus(): Promise<RecoveryCodesStatus> {
  const res = await apiClient.get<RecoveryCodesStatus>('/api/auth/recovery-codes/status');
  return res.data;
}

/** Pre-auth, LAN-only. Raw fetch (no bearer). Throws with the server's message. */
export async function recoveryReset(username: string, recoveryCode: string, newPassword: string): Promise<{ message: string }> {
  const res = await fetch(buildApiUrl('/api/auth/recovery-reset'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, recovery_code: recoveryCode, new_password: newPassword }),
  });
  const data = (await res.json().catch(() => ({}))) as { message?: string; detail?: unknown };
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === 'string' ? d
      : d && typeof d === 'object' && 'message' in d ? String((d as { message: unknown }).message)
      : `Reset failed (${res.status})`;
    throw new Error(msg);
  }
  return { message: String(data.message ?? 'Password reset successfully') };
}
