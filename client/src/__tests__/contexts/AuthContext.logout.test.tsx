import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { queryClient } from '../../lib/queryClient';
import { queryPersister } from '../../lib/queryPersister';

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
});
