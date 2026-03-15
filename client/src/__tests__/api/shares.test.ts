import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getShareableUsers,
  createFileShare,
  listFileSharesForFile,
  listFilesSharedWithMe,
  updateFileShare,
  deleteFileShare,
  getShareStatistics,
} from '../../api/shares';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  apiCache: { delete: vi.fn() },
  memoizedApiRequest: vi.fn(),
}));

import { apiClient, apiCache } from '../../lib/api';

describe('shares API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.delete).mockReset();
    vi.mocked(apiCache.delete).mockReset();
  });

  it('getShareableUsers calls GET /api/shares/users', async () => {
    const users = [{ id: 1, username: 'user1' }];
    vi.mocked(apiClient.get).mockResolvedValue({ data: users });

    const result = await getShareableUsers();

    expect(apiClient.get).toHaveBeenCalledWith('/api/shares/users');
    expect(result).toEqual(users);
  });

  it('createFileShare calls POST and clears cache', async () => {
    const shareData = { file_id: 10, shared_with_user_id: 2, can_read: true };
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 1, ...shareData } });

    const result = await createFileShare(shareData);

    expect(apiClient.post).toHaveBeenCalledWith('/api/shares/user-shares', shareData);
    expect(apiCache.delete).toHaveBeenCalled();
    expect(result.file_id).toBe(10);
  });

  it('listFileSharesForFile calls GET with fileId', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

    await listFileSharesForFile(42);

    expect(apiClient.get).toHaveBeenCalledWith('/api/shares/user-shares/file/42');
  });

  it('listFilesSharedWithMe calls GET /api/shares/shared-with-me', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

    await listFilesSharedWithMe();

    expect(apiClient.get).toHaveBeenCalledWith('/api/shares/shared-with-me');
  });

  it('updateFileShare calls PATCH and clears cache', async () => {
    const update = { can_write: true };
    vi.mocked(apiClient.patch).mockResolvedValue({ data: { id: 5, ...update } });

    await updateFileShare(5, update);

    expect(apiClient.patch).toHaveBeenCalledWith('/api/shares/user-shares/5', update);
    expect(apiCache.delete).toHaveBeenCalled();
  });

  it('deleteFileShare calls DELETE and clears cache', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({});

    await deleteFileShare(3);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/shares/user-shares/3');
    expect(apiCache.delete).toHaveBeenCalled();
  });

  it('getShareStatistics calls GET /api/shares/statistics', async () => {
    const stats = { total_file_shares: 10, active_file_shares: 8, files_shared_with_me: 3 };
    vi.mocked(apiClient.get).mockResolvedValue({ data: stats });

    const result = await getShareStatistics();

    expect(apiClient.get).toHaveBeenCalledWith('/api/shares/statistics');
    expect(result).toEqual(stats);
  });
});
