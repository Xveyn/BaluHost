import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  bulkDeleteUsers,
  toggleUserActive,
  updateUserEmail,
} from '../../api/users';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from '../../lib/api';

describe('users API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it('listUsers calls GET /api/users/ with params', async () => {
    const mockResponse = { users: [], total: 0, active: 0, inactive: 0, admins: 0 };
    vi.mocked(apiClient.get).mockResolvedValue({ data: mockResponse });

    const result = await listUsers({ search: 'admin', role: 'admin' });

    expect(apiClient.get).toHaveBeenCalledWith('/api/users/', {
      params: { search: 'admin', role: 'admin' },
    });
    expect(result).toEqual(mockResponse);
  });

  it('createUser calls POST /api/users/', async () => {
    const newUser = { username: 'testuser', password: 'Pass123!' };
    const mockUser = { id: 1, username: 'testuser', role: 'user' };
    vi.mocked(apiClient.post).mockResolvedValue({ data: mockUser });

    const result = await createUser(newUser);

    expect(apiClient.post).toHaveBeenCalledWith('/api/users/', newUser);
    expect(result).toEqual(mockUser);
  });

  it('updateUser calls PUT /api/users/:id', async () => {
    const payload = { email: 'new@example.com' };
    vi.mocked(apiClient.put).mockResolvedValue({ data: { id: 5, ...payload } });

    await updateUser(5, payload);

    expect(apiClient.put).toHaveBeenCalledWith('/api/users/5', payload);
  });

  it('deleteUser calls DELETE /api/users/:id', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({});

    await deleteUser(7);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/users/7');
  });

  it('bulkDeleteUsers calls POST /api/users/bulk-delete', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { deleted: 3 } });

    const result = await bulkDeleteUsers([1, 2, 3]);

    expect(apiClient.post).toHaveBeenCalledWith('/api/users/bulk-delete', [1, 2, 3]);
    expect(result).toEqual({ deleted: 3 });
  });

  it('toggleUserActive calls PATCH /api/users/:id/toggle-active', async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: { id: 2, is_active: false } });

    const result = await toggleUserActive(2);

    expect(apiClient.patch).toHaveBeenCalledWith('/api/users/2/toggle-active');
    expect(result.is_active).toBe(false);
  });

  it('updateUserEmail calls PATCH /api/users/:id', async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: { id: 3, email: 'x@y.com' } });

    await updateUserEmail(3, 'x@y.com');

    expect(apiClient.patch).toHaveBeenCalledWith('/api/users/3', { email: 'x@y.com' });
  });
});
