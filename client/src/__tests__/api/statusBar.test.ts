import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getStatusBarState, updateStatusBarConfig } from '../../api/statusBar';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), put: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('statusBar api', () => {
  it('getStatusBarState calls the state endpoint and returns data', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { pills: [], show_bottom_upload: true } });
    const result = await getStatusBarState();
    expect(apiClient.get).toHaveBeenCalledWith('/api/system/statusbar/state');
    expect(result.show_bottom_upload).toBe(true);
  });

  it('updateStatusBarConfig PUTs the payload', async () => {
    (apiClient.put as any).mockResolvedValue({ data: { pills: [], show_bottom_upload: false } });
    await updateStatusBarConfig({ pills: [], show_bottom_upload: false });
    expect(apiClient.put).toHaveBeenCalledWith('/api/system/statusbar/config', { pills: [], show_bottom_upload: false });
  });
});
