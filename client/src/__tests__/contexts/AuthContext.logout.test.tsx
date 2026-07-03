import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { queryClient } from '../../lib/queryClient';
import { queryPersister } from '../../lib/queryPersister';
import type { User } from '../../types/auth';

vi.spyOn(queryClient, 'clear').mockImplementation(() => {});
vi.spyOn(queryPersister, 'removeClient').mockResolvedValue(undefined);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>;

describe('AuthContext logout', () => {
  it('clears the in-memory query cache and the persisted blob', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => {
      result.current.logout();
    });
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
    expect(queryPersister.removeClient).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('login clears any cached data from a previous session', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => {
      result.current.login({ id: 1, username: 'bob', role: 'user' } as unknown as User, 'new-token');
    });
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
    expect(queryPersister.removeClient).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('token')).toBe('new-token');
  });

  it('auth:expired (plain, no impersonation) clears the query cache', () => {
    localStorage.setItem('token', 'expired-token');
    renderHook(() => useAuth(), { wrapper });
    act(() => {
      window.dispatchEvent(new CustomEvent('auth:expired'));
    });
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
    expect(queryPersister.removeClient).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('token')).toBeNull();
  });
});
