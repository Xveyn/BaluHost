import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { buildApiUrl } from '../lib/api';
import { queryClient } from '../lib/queryClient';
import { queryPersister } from '../lib/queryPersister';
import { impersonateUser as apiImpersonateUser } from '../api/authDev';
import type { User } from '../types/auth';

const ORIGIN_TOKEN_KEY = 'impersonation_origin_token';
const ORIGIN_USERNAME_KEY = 'impersonation_origin_username';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (user: User, token: string) => void;
  logout: () => void;
  isAdmin: boolean;
  loading: boolean;
  isImpersonating: boolean;
  impersonationOrigin: string | null;
  impersonate: (userId: number) => Promise<void>;
  endImpersonation: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchMe(token: string): Promise<User | null> {
  try {
    const res = await fetch(buildApiUrl('/api/auth/me'), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.user || data;
  } catch {
    return null;
  }
}

/**
 * Drop all cached queries and the persisted sessionStorage blob.
 * MUST run on EVERY identity change (login, logout, impersonation swaps,
 * auth expiry) — user-scoped queries (#299) would otherwise leak across
 * users via the persister's F5 instant-paint.
 */
function clearQueryCache(): void {
  queryClient.clear();
  void queryPersister.removeClient();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [impersonationOrigin, setImpersonationOrigin] = useState<string | null>(
    () => sessionStorage.getItem(ORIGIN_USERNAME_KEY),
  );

  const isImpersonating = impersonationOrigin !== null;

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (!storedToken) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setToken(storedToken);
    fetch(buildApiUrl('/api/auth/me'), {
      headers: { Authorization: `Bearer ${storedToken}` },
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error('Token invalid');
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        const userData = data.user || data;
        if (userData?.username) {
          setUser(userData);
        } else {
          throw new Error('Invalid user data');
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        localStorage.removeItem('token');
        sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
        sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
        setImpersonationOrigin(null);
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const login = (userData: User, newToken: string) => {
    // A previous session on this tab (e.g. ended via auth:expired) may have
    // left user-scoped data in the cache/persister — never show it to the
    // next account.
    clearQueryCache();
    localStorage.setItem('token', newToken);
    setToken(newToken);
    setUser(userData);
  };

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    setImpersonationOrigin(null);
    setToken(null);
    setUser(null);
    // Drop any cached data for the ended session so a next login on the same
    // tab can't briefly show it before refetch (see clearQueryCache).
    clearQueryCache();
  }, []);

  const impersonate = useCallback(async (userId: number) => {
    const currentToken = localStorage.getItem('token');
    const currentUsername = user?.username;
    if (!currentToken || !currentUsername) {
      throw new Error('Cannot impersonate: no active session');
    }

    const result = await apiImpersonateUser(userId);

    sessionStorage.setItem(ORIGIN_TOKEN_KEY, currentToken);
    sessionStorage.setItem(ORIGIN_USERNAME_KEY, currentUsername);
    localStorage.setItem('token', result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    setImpersonationOrigin(currentUsername);
    clearQueryCache();
  }, [user]);

  const endImpersonation = useCallback(() => {
    const originToken = sessionStorage.getItem(ORIGIN_TOKEN_KEY);
    if (!originToken) {
      logout();
      return;
    }

    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    localStorage.setItem('token', originToken);
    setToken(originToken);
    setImpersonationOrigin(null);
    clearQueryCache();

    fetchMe(originToken).then((restoredUser) => {
      if (restoredUser) {
        setUser(restoredUser);
      } else {
        logout();
      }
    });
  }, [logout]);

  // Listen for global auth:expired events (from 401 interceptor or raw fetch handlers)
  useEffect(() => {
    const handler = () => {
      const originToken = sessionStorage.getItem(ORIGIN_TOKEN_KEY);
      if (originToken) {
        // Impersonation session expired — try to restore admin session
        sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
        sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
        localStorage.setItem('token', originToken);
        setToken(originToken);
        setImpersonationOrigin(null);
        clearQueryCache();
        fetchMe(originToken).then((restoredUser) => {
          if (restoredUser) {
            setUser(restoredUser);
          } else {
            setToken(null);
            setUser(null);
            localStorage.removeItem('token');
          }
        });
      } else {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
        clearQueryCache();
      }
    };
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        isAdmin: user?.role === 'admin',
        loading,
        isImpersonating,
        impersonationOrigin,
        impersonate,
        endImpersonation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
