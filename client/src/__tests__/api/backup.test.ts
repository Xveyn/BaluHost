import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listBackups, createBackup, deleteBackup, restoreBackup } from '../../api/backup';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  buildApiUrl: (p: string) => p,
}));

import { apiClient } from '../../lib/api';

describe('backup API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it('listBackups calls GET /api/backups/ directly (no memo cache)', async () => {
    const payload = { backups: [], total_size_bytes: 0, total_size_mb: 0 };
    vi.mocked(apiClient.get).mockResolvedValue({ data: payload });

    const result = await listBackups();

    expect(apiClient.get).toHaveBeenCalledWith('/api/backups/');
    expect(result).toEqual(payload);
  });

  it('createBackup posts the request body', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 1 } });

    await createBackup({ includes_database: true });

    expect(apiClient.post).toHaveBeenCalledWith('/api/backups/', { includes_database: true });
  });

  it('restoreBackup leaves the auth header to the apiClient interceptor', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { success: true } });
    const request = { backup_id: 3, confirm: true };

    await restoreBackup(request);

    // Kein drittes Argument: ein eigener Authorization-Header würde den
    // Interceptor in lib/api.ts doppeln (und bei fehlendem Token
    // "Bearer null" senden).
    expect(apiClient.post).toHaveBeenCalledWith('/api/backups/3/restore', request);
    expect(vi.mocked(apiClient.post).mock.calls[0]).toHaveLength(2);
  });

  it('deleteBackup calls DELETE with the id', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({});

    await deleteBackup(7);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/backups/7');
  });
});
