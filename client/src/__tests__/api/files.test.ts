import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  checkFilesExist,
  getFilePermissions,
  setFilePermissions,
  transferOwnership,
  enforceResidency,
} from '../../api/files';

vi.mock('../../lib/api', () => ({
  apiClient: {
    post: vi.fn(),
    put: vi.fn(),
  },
  memoizedApiRequest: vi.fn(),
}));

import { apiClient, memoizedApiRequest } from '../../lib/api';

describe('files API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(memoizedApiRequest).mockReset();
  });

  it('checkFilesExist posts filenames and target path', async () => {
    const mockResult = { duplicates: [{ filename: 'a.txt', size_bytes: 100 }] };
    vi.mocked(apiClient.post).mockResolvedValue({ data: mockResult });

    const result = await checkFilesExist(['a.txt', 'b.txt'], '/docs');

    expect(apiClient.post).toHaveBeenCalledWith('/api/files/check-exists', {
      filenames: ['a.txt', 'b.txt'],
      target_path: '/docs',
    });
    expect(result.duplicates).toHaveLength(1);
  });

  it('getFilePermissions uses memoizedApiRequest', async () => {
    vi.mocked(memoizedApiRequest).mockResolvedValue({ owner_id: 1, rules: [] });

    await getFilePermissions('/my/file.txt');

    expect(memoizedApiRequest).toHaveBeenCalledWith('/api/files/permissions', { path: '/my/file.txt' });
  });

  it('setFilePermissions calls PUT /api/files/permissions', async () => {
    const permData = {
      path: '/my/file.txt',
      owner_id: 1,
      rules: [{ user_id: 2, can_view: true, can_edit: false, can_delete: false }],
    };
    vi.mocked(apiClient.put).mockResolvedValue({ data: { success: true } });

    await setFilePermissions(permData);

    expect(apiClient.put).toHaveBeenCalledWith('/api/files/permissions', permData);
  });

  it('transferOwnership posts request body', async () => {
    const request = { path: '/docs', new_owner_id: 2, recursive: true };
    const response = { success: true, message: 'Transferred', transferred_count: 5 };
    vi.mocked(apiClient.post).mockResolvedValue({ data: response });

    const result = await transferOwnership(request);

    expect(apiClient.post).toHaveBeenCalledWith('/api/files/transfer-ownership', request);
    expect(result.success).toBe(true);
    expect(result.transferred_count).toBe(5);
  });

  it('enforceResidency posts dry_run flag', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { violations: [], fixed_count: 0 } });

    const result = await enforceResidency({ dry_run: true });

    expect(apiClient.post).toHaveBeenCalledWith('/api/files/enforce-residency', { dry_run: true });
    expect(result.violations).toEqual([]);
  });
});
