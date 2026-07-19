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

// Mount counter: UserMenu is unconditionally rendered inside LayoutHeader, so
// its own mount count is a proxy for "did Layout (and everything inside it)
// remount". The test below expects this to stay at 1 across a navigation —
// if a future edit ever reintroduces a scenario where Layout genuinely
// remounts, this counter would tick to 2 and the assertion would catch it.
// Proxy caveat: this only works because UserMenu is unconditionally present
// in LayoutHeader. If UserMenu ever becomes conditional or moves out of
// LayoutHeader, this counter breaks for reasons unrelated to Layout's own
// mount lifecycle — re-anchor it to a different always-present child if that happens.
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

// Die übrigen sechs admin-guarded Seiten (isAdmin ? <Page/> : <Navigate to="/"/>) —
// je ein Mock, damit eine nicht-Admin-Navigation dorthin geprüft werden kann.
vi.mock('../pages/AdminDatabase', () => ({ default: () => <div data-testid="admindb-page" /> }));
vi.mock('../pages/SchedulerDashboard', () => ({ default: () => <div data-testid="schedulers-page" /> }));
vi.mock('../pages/SystemControlPage', () => ({ default: () => <div data-testid="systemcontrol-page" /> }));
vi.mock('../pages/PluginsPage', () => ({ default: () => <div data-testid="plugins-page" /> }));
vi.mock('../pages/UpdatePage', () => ({ default: () => <div data-testid="updates-page" /> }));
vi.mock('../pages/PiholePage', () => ({ default: () => <div data-testid="pihole-page" /> }));

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

  // The cold-start logged-out case above only proves the guard works on first
  // render. The parent-route guard (`user ? <AppLayout/> : <Navigate to="/login"
  // replace/>`) is now the single point of failure for auth across all 18
  // child routes, so the interesting direction is the transition: user becomes
  // null on an already-mounted, already-authenticated tree — logout or a token
  // expiring mid-session — not just a page loaded while logged out.
  it('Logout während laufender Session (Tree bereits gemountet) → redirect auf /login', async () => {
    const { rerender } = render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(window.location.pathname).toBe('/');

    authState.user = null;
    authState.isAdmin = false;
    rerender(<AppRoutes />);

    await screen.findByTestId('login-page');
    expect(window.location.pathname).toBe('/login');
  });

  // Alle sieben admin-guarded Routen (isAdmin ? <Page/> : <Navigate to="/"/>) —
  // ein geflipptes Guard ist das dominante Risiko dieses Refactors.
  it.each([
    ['/users', 'users-page'],
    ['/admin-db', 'admindb-page'],
    ['/schedulers', 'schedulers-page'],
    ['/admin/system-control', 'systemcontrol-page'],
    ['/plugins', 'plugins-page'],
    ['/updates', 'updates-page'],
    ['/pihole', 'pihole-page'],
  ])('Nicht-Admin auf %s → redirect auf Dashboard', async (path, testId) => {
    authState.isAdmin = false;
    authState.user = { id: 2, username: 'user', role: 'user' };
    window.history.pushState({}, '', path);
    render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
  });
});
