import { describe, it, expect, vi, beforeEach } from 'vitest';
import { generateRecoveryCodes, getRecoveryCodesStatus } from '../../api/recovery-codes';
import { apiClient } from '../../lib/api';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn() }, buildApiUrl: (p: string) => p };
});

describe('recovery-codes api', () => {
  beforeEach(() => vi.clearAllMocks());

  it('generateRecoveryCodes posts step-up body and unwraps data', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { recovery_codes: ['A', 'B'] } });
    const res = await generateRecoveryCodes({ current_password: 'pw' });
    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/recovery-codes', { current_password: 'pw' });
    expect(res.recovery_codes).toEqual(['A', 'B']);
  });

  it('getRecoveryCodesStatus unwraps data', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { configured: true, remaining: 9 } });
    expect(await getRecoveryCodesStatus()).toEqual({ configured: true, remaining: 9 });
  });
});
