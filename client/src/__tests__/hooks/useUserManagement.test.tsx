import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useUserManagement } from '../../hooks/useUserManagement';
import * as usersApi from '../../api/users';
import type { UserPublic, UsersResponse } from '../../api/users';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
  getApiErrorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}));

vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true), dialog: null }),
}));

vi.mock('../../api/users');
const api = vi.mocked(usersApi);

function user(overrides: Partial<UserPublic>): UserPublic {
  return {
    id: 1,
    username: 'alice',
    email: 'a@example.com',
    role: 'admin',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    ...overrides,
  };
}

const usersResponse: UsersResponse = {
  users: [user({ id: 1, role: 'admin', is_active: true }), user({ id: 2, username: 'bob', role: 'user', is_active: false })],
  total: 2,
  active: 1,
  inactive: 1,
  admins: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listUsers.mockResolvedValue(usersResponse);
});

describe('useUserManagement', () => {
  it('loads users and derives stats', async () => {
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.users).toHaveLength(2);
    expect(result.current.stats).toEqual({ total: 2, active: 1, inactive: 1, admins: 1 });
    expect(result.current.error).toBeNull();
  });

  it('refetches with the new params when the role filter changes', async () => {
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      result.current.setRoleFilter('admin');
    });
    await waitFor(() =>
      expect(api.listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ role: 'admin' })),
    );
  });

  it('handleCreateUser creates, returns true and refetches', async () => {
    api.createUser.mockResolvedValue(user({ id: 3, username: 'carol', role: 'user' }));
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = api.listUsers.mock.calls.length;

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.handleCreateUser({
        username: 'carol',
        email: '',
        password: 'Secret123',
        role: 'user',
        is_active: true,
      });
    });

    expect(ok).toBe(true);
    expect(api.createUser).toHaveBeenCalledWith({ username: 'carol', password: 'Secret123', role: 'user', email: undefined });
    await waitFor(() => expect(api.listUsers.mock.calls.length).toBeGreaterThan(before));
  });

  it('handleCreateUser rejects an empty username without calling the API', async () => {
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.handleCreateUser({
        username: '',
        email: '',
        password: '',
        role: 'user',
        is_active: true,
      });
    });

    expect(ok).toBe(false);
    expect(api.createUser).not.toHaveBeenCalled();
  });

  it('handleToggleActive calls the API', async () => {
    api.toggleUserActive.mockResolvedValue(user({ id: 1, is_active: false }));
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleActive(1);
    });
    expect(api.toggleUserActive).toHaveBeenCalledWith(1);
  });

  it('surfaces an error string when the list fetch fails', async () => {
    api.listUsers.mockReset();
    api.listUsers.mockRejectedValue(new Error('users boom'));
    const { result } = renderHook(() => useUserManagement(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.error).toBe('users boom'));
  });
});
