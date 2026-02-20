import { describe, it, expect, vi, beforeEach } from 'vitest';
import { requestConfirmation, executeConfirmation } from '../../api/raid';

vi.mock('../../lib/api', () => ({
  apiClient: { post: vi.fn() },
}));

import { apiClient } from '../../lib/api';

describe('raid api confirmation helpers', () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
  });

  it('requestConfirmation posts action and payload and returns token', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { token: 'tok-123', expires_at: 9999999999 },
    });

    const res = await requestConfirmation('delete_array', { array: 'md0' });
    expect(res).toEqual({ token: 'tok-123', expires_at: 9999999999 });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/system/raid/confirm/request',
      { action: 'delete_array', payload: { array: 'md0' } },
    );
  });

  it('executeConfirmation posts token and returns message', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { message: 'Executed' },
    });

    const res = await executeConfirmation('tok-123');
    expect(res).toEqual({ message: 'Executed' });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/system/raid/confirm/execute',
      { token: 'tok-123' },
    );
  });
});
