import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getScopeCatalog } from '../../api/plugins';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn() },
}));

describe('getScopeCatalog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('maps the scope-catalog response', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        scopes: [
          { key: 'read:system-info', tier: 'frontend', dangerous: false },
          { key: 'storage', tier: 'backend', dangerous: false },
        ],
      },
    });
    const res = await getScopeCatalog();
    expect(apiClient.get).toHaveBeenCalledWith('/api/plugins/scope-catalog');
    expect(res.scopes).toHaveLength(2);
    expect(res.scopes[0].tier).toBe('frontend');
  });
});
