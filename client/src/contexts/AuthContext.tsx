import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { buildApiUrl } from '../lib/api';
import type { User } from '../types/auth';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (user: User, token: string) => void;
  logout: () => void;
  isAdmin: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (!storedToken) {
      setLoading(false);
      return;
    }

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
        const userData = data.user || data;
        if (userData?.username) {
          setUser(userData);
        } else {
          throw new Error('Invalid user data');
        }
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, []);

  const login = (userData: User, newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  };

  // Listen for global auth:expired events (from 401 interceptor or raw fetch handlers)
  useEffect(() => {
    const handler = () => {
      setToken(null);
      setUser(null);
    };
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAdmin: user?.role === 'admin', loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
