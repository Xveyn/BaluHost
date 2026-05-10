import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as twoFactorApi from '../../../api/two-factor';
import { loadStatusOnce, refreshStatus } from '../../../components/quickSettings/twoFactorStatusStore';

describe('twoFactorStatusStore', () => {
  beforeEach(() => {
    refreshStatus();
    vi.restoreAllMocks();
  });

  it('first call hits the API once', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledOnce();
  });

  it('second call returns cached value without hitting the API again', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: true,
      enabled_at: '2026-01-01T00:00:00Z',
      backup_codes_remaining: 5,
    });
    await loadStatusOnce();
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledOnce();
  });

  it('refreshStatus invalidates so next call hits the API again', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await loadStatusOnce();
    refreshStatus();
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('failed request resolves to null and does not throw', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockRejectedValue(new Error('network'));
    const result = await loadStatusOnce();
    expect(result).toBeNull();
  });

  it('concurrent calls share a single in-flight request', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await Promise.all([loadStatusOnce(), loadStatusOnce(), loadStatusOnce()]);
    expect(spy).toHaveBeenCalledOnce();
  });
});
