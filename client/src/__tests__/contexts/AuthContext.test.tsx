import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { ReactNode } from 'react';

// Mock the api module before importing AuthContext
vi.mock('../../lib/api', () => ({
  buildApiUrl: (path: string) => path,
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  API_BASE_URL: '',
}));

import { AuthProvider, useAuth } from '../../contexts/AuthContext';

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('AuthContext', () => {
  const mockUser = { id: 1, username: 'admin', role: 'admin', email: 'admin@test.com' };
  let mockLocalStorage: Record<string, string>;

  beforeEach(() => {
    mockLocalStorage = {};
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(
      (key: string) => mockLocalStorage[key] ?? null
    );
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(
      (key: string, value: string) => { mockLocalStorage[key] = value; }
    );
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(
      (key: string) => { delete mockLocalStorage[key]; }
    );
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('throws error when useAuth is used outside AuthProvider', () => {
    // Suppress React and jsdom error output
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      renderHook(() => useAuth());
    }).toThrow('useAuth must be used within an AuthProvider');

    errorSpy.mockRestore();
  });

  it('returns null user and loading=false when no stored token', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAdmin).toBe(false);
  });

  it('validates stored token and sets user on success', async () => {
    mockLocalStorage['token'] = 'valid-token';

    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockUser),
    } as Response);

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.isAdmin).toBe(true);

    expect(fetch).toHaveBeenCalledWith('/api/auth/me', {
      headers: { Authorization: 'Bearer valid-token' },
    });
  });

  it('handles nested user data format', async () => {
    mockLocalStorage['token'] = 'valid-token';

    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ user: mockUser }),
    } as Response);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);
  });

  it('removes stored token when validation fails', async () => {
    mockLocalStorage['token'] = 'invalid-token';

    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Token expired' }),
    } as Response);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.removeItem).toHaveBeenCalledWith('token');
  });

  it('login() saves token and sets user', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.login(mockUser, 'new-token');
    });

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.token).toBe('new-token');
    expect(result.current.isAdmin).toBe(true);
    expect(localStorage.setItem).toHaveBeenCalledWith('token', 'new-token');
  });

  it('logout() clears user and token', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.login(mockUser, 'some-token');
    });

    expect(result.current.user).not.toBeNull();

    act(() => {
      result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAdmin).toBe(false);
    expect(localStorage.removeItem).toHaveBeenCalledWith('token');
  });

  it('isAdmin is false for non-admin users', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.login({ id: 2, username: 'user', role: 'user' }, 'token');
    });

    expect(result.current.isAdmin).toBe(false);
  });
});
