import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  buildApiUrl: (p: string) => p,
}));

import { apiClient } from '../../lib/api';
import { getPinStatus, setPin, removePin } from '../../api/pin';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('pin api client', () => {
  it('getPinStatus returns pin_enabled', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { pin_enabled: true } } as any);
    const r = await getPinStatus();
    expect(r.pin_enabled).toBe(true);
    expect(apiClient.get).toHaveBeenCalledWith('/api/auth/pin');
  });

  it('setPin posts pin + code', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { message: 'PIN set' } } as any);
    await setPin('4827', '123456');
    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/pin', { pin: '4827', code: '123456' });
  });

  it('removePin sends code in the request body', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { message: 'PIN removed' } } as any);
    await removePin('123456');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/auth/pin', { data: { code: '123456' } });
  });
});
