import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppRoutes } from '../App';

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin', role: 'admin' } as { id: number; username: string; role: string } | null,
  isAdmin: true,
  isImpersonating: false,
  loading: false,
  logout: vi.fn(),
}));
const mountCount = vi.hoisted(() => ({ current: 0 }));
const getStatusBarStateMock = vi.hoisted(() =>
  vi.fn(async () => ({ pills: [], show_bottom_upload: true })),
);

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginNavItems: [] }),
  PluginProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/VersionContext', () => ({
  useFormattedVersion: () => 'v1.38.0',
  VersionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/UploadContext', () => ({
  UploadProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/NotificationContext', () => ({
  NotificationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../hooks/useIdleTimeout', () => ({
  useIdleTimeout: () => ({ warningVisible: false, secondsRemaining: 0, resetTimer: vi.fn() }),
}));
vi.mock('../hooks/usePresenceHeartbeat', () => ({ usePresenceHeartbeat: vi.fn() }));
vi.mock('../api/statusBar', () => ({ getStatusBarState: getStatusBarStateMock }));
vi.mock('../lib/localApi', () => ({
  localApi: { shutdown: vi.fn(), restart: vi.fn(), isAvailable: vi.fn() },
}));
vi.mock('../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, f: string) => f,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Schwere Layout-Kinder
vi.mock('../components/NotificationCenter', () => ({ default: () => null }));
vi.mock('../components/PowerMenu', () => ({ default: () => null }));
vi.mock('../components/UploadProgressBar', () => ({ UploadProgressBar: () => null }));
vi.mock('../components/topbar/TopbarStatusStrip', () => ({ TopbarStatusStrip: () => null }));
vi.mock('../components/ImpersonationBanner', () => ({ default: () => null }));

// Mount-Zähler: UserMenu ist immer im Header — remountet Layout, zählt er hoch.
// Named (capitalized) component fn, not an anonymous `default: () => ...` —
// eslint's react-hooks/rules-of-hooks needs a component-shaped name to allow the useEffect call.
vi.mock('../components/UserMenu', async () => {
  const { useEffect } = await import('react');
  function MockUserMenu() {
    useEffect(() => { mountCount.current += 1; }, []);
    return <div data-testid="user-menu" />;
  }
  return { default: MockUserMenu };
});

// Seiten, die der Test besucht (lazy → Mock-Module lösen sofort auf)
vi.mock('../pages/Dashboard', () => ({ default: () => <div data-testid="dashboard-page" /> }));
vi.mock('../pages/SystemMonitor', () => ({ default: () => <div data-testid="system-page" /> }));
vi.mock('../pages/UserManagement', () => ({ default: () => <div data-testid="users-page" /> }));
vi.mock('../pages/Login', () => ({ default: () => <div data-testid="login-page" /> }));

beforeEach(() => {
  authState.user = { id: 1, username: 'admin', role: 'admin' };
  authState.isAdmin = true;
  mountCount.current = 0;
  getStatusBarStateMock.mockClear();
  window.history.pushState({}, '', '/');
});

describe('App routing mit Layout-Route', () => {
  it('Layout bleibt über Navigation gemountet; StatusBar fetcht nur einmal pro Layout-Mount', async () => {
    render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(mountCount.current).toBe(1);
    const fetchesBefore = getStatusBarStateMock.mock.calls.length;
    expect(fetchesBefore).toBeGreaterThan(0); // initial fetch on mount happened

    // Desktop-Sidebar-Link "System" klicken (erster von zwei)
    fireEvent.click(screen.getAllByText('navigation.system')[0]);
    await screen.findByTestId('system-page');

    expect(mountCount.current).toBe(1); // KEIN Remount
    // Layout's getStatusBarState effect has `[]` deps (fetch once per mount, not
    // per navigation) — this matches the pre-refactor original, which never
    // remounted Layout on navigation either (see task-6-report.md). No new
    // fetch should have happened just from navigating.
    expect(getStatusBarStateMock.mock.calls.length).toBe(fetchesBefore);
  });

  it('ausgeloggt → /login', async () => {
    authState.user = null;
    authState.isAdmin = false;
    render(<AppRoutes />);
    await screen.findByTestId('login-page');
    expect(window.location.pathname).toBe('/login');
  });

  it('Nicht-Admin auf /users → redirect auf Dashboard', async () => {
    authState.isAdmin = false;
    authState.user = { id: 2, username: 'user', role: 'user' };
    window.history.pushState({}, '', '/users');
    render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(screen.queryByTestId('users-page')).not.toBeInTheDocument();
  });
});
