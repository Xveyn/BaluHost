import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../../components/Layout';

// ---- Mutable Mock-Zustände (vor den vi.mock-Hoists) ----
const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin', role: 'admin' } as { id: number; username: string; role: string } | null,
  isAdmin: true,
  isImpersonating: false,
  logout: vi.fn(),
}));
const featureState = vi.hoisted(() => ({ isPi: false }));
const pluginState = vi.hoisted(() => ({ pluginNavItems: [] as Array<{ path: string; label: string; admin_only: boolean }> }));
const getStatusBarStateMock = vi.hoisted(() =>
  vi.fn(async () => ({ pills: [], show_bottom_upload: true })),
);

// ---- Kontext-Mocks ----
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => pluginState }));
vi.mock('../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));
vi.mock('../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, fallback: string) => fallback,
}));
vi.mock('../../api/statusBar', () => ({ getStatusBarState: getStatusBarStateMock }));
vi.mock('../../lib/localApi', () => ({
  localApi: { shutdown: vi.fn(), restart: vi.fn(), isAvailable: vi.fn() },
}));

// ---- Schwere Kinder per Modulpfad mocken (überleben den Refactor) ----
vi.mock('../../components/NotificationCenter', () => ({
  default: () => <div data-testid="notification-center" />,
}));
vi.mock('../../components/PowerMenu', () => ({
  default: () => <div data-testid="power-menu" />,
}));
vi.mock('../../components/UserMenu', () => ({
  default: () => <div data-testid="user-menu" />,
}));
vi.mock('../../components/UploadProgressBar', () => ({
  UploadProgressBar: () => <div data-testid="upload-progress-bar" />,
}));
vi.mock('../../components/topbar/TopbarStatusStrip', () => ({
  TopbarStatusStrip: () => <div data-testid="topbar-status-strip" />,
}));
vi.mock('../../components/ImpersonationBanner', () => ({ default: () => null }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Layout calls t(key), t(key, 'fallback string'), and t(key, 'fallback', { options }) —
    // extra args are simply ignored by JS, so returning the key always is safe for all three shapes.
    t: (key: string) => key,
  }),
}));

function renderLayout(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <div data-testid="page-content" />
      </Layout>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  authState.user = { id: 1, username: 'admin', role: 'admin' };
  authState.isAdmin = true;
  authState.isImpersonating = false;
  featureState.isPi = false;
  pluginState.pluginNavItems = [];
  getStatusBarStateMock.mockClear();
  getStatusBarStateMock.mockResolvedValue({ pills: [], show_bottom_upload: true });
});

describe('Layout (Charakterisierung)', () => {
  it('rendert children und beide Sidebars mit Brand', () => {
    renderLayout();
    expect(screen.getByTestId('page-content')).toBeInTheDocument();
    // Desktop-Sidebar + Mobile-Sidebar + Mobile-Header-Brand = 3x "BaluHost"
    expect(screen.getAllByText('BaluHost')).toHaveLength(3);
  });

  it('Admin sieht Admin-Items und Admin-Trenner in beiden Sidebars', () => {
    renderLayout();
    expect(screen.getAllByText('navigation.users')).toHaveLength(2);
    expect(screen.getAllByText('navigation.updates')).toHaveLength(2);
    expect(screen.getAllByText('navigation.admin')).toHaveLength(2);
  });

  it('Nicht-Admin sieht weder Admin-Items noch Trenner', () => {
    authState.isAdmin = false;
    authState.user = { id: 2, username: 'user', role: 'user' };
    renderLayout();
    expect(screen.queryAllByText('navigation.users')).toHaveLength(0);
    expect(screen.queryAllByText('navigation.admin')).toHaveLength(0);
    expect(screen.getAllByText('navigation.dashboard')).toHaveLength(2);
  });

  it('Pi-Mode: nur Dashboard+System, Brand BaluPi, kein NotificationCenter, keine UploadBar', async () => {
    featureState.isPi = true;
    renderLayout();
    expect(screen.getAllByText('navigation.dashboard')).toHaveLength(2);
    expect(screen.getAllByText('navigation.system')).toHaveLength(2);
    expect(screen.queryAllByText('navigation.files')).toHaveLength(0);
    expect(screen.getAllByText('BaluPi')).toHaveLength(3);
    expect(screen.queryByTestId('notification-center')).not.toBeInTheDocument();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    expect(screen.queryByTestId('upload-progress-bar')).not.toBeInTheDocument();
  });

  it('Plugin-Nav-Items erscheinen; admin_only-Plugins sind für Nicht-Admins gefiltert', () => {
    pluginState.pluginNavItems = [
      { path: 'demo', label: 'DemoPlugin', admin_only: false },
      { path: 'secret', label: 'SecretPlugin', admin_only: true },
    ];
    authState.isAdmin = false;
    renderLayout();
    expect(screen.getAllByText('DemoPlugin')).toHaveLength(2);
    expect(screen.queryAllByText('SecretPlugin')).toHaveLength(0);
  });

  it('/admin-db bekommt volle Breite, andere Routen max-w-7xl', () => {
    const { container, unmount } = renderLayout('/admin-db');
    expect(container.querySelector('main > div')!.className).toContain('max-w-none');
    unmount();
    const { container: c2 } = renderLayout('/');
    expect(c2.querySelector('main > div')!.className).toContain('max-w-7xl');
  });

  it('Impersonation verschiebt Header und Main', () => {
    authState.isImpersonating = true;
    const { container, unmount } = renderLayout();
    expect(container.querySelector('header')!.className).toContain('top-10');
    expect(container.querySelector('main')!.className).toContain('mt-[112px]');
    unmount();
    authState.isImpersonating = false;
    const { container: c2 } = renderLayout();
    expect(c2.querySelector('header')!.className).toContain('top-0');
    expect(c2.querySelector('main')!.className).toContain('mt-[72px]');
  });

  it('Mobile-Menü öffnet per Hamburger und schließt per Overlay-Klick', async () => {
    const { container } = renderLayout();
    // Pending getStatusBarState-Effect abwarten, bevor Events gefeuert werden (vermeidet act()-Warnung)
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    const mobileAside = () =>
      Array.from(container.querySelectorAll('aside')).find((a) => a.className.includes('z-50'))!;
    expect(mobileAside().className).toContain('-translate-x-full');
    // Hamburger = erster Button im Header
    fireEvent.click(container.querySelector('header button')!);
    expect(mobileAside().className).toContain('translate-x-0');
    // Overlay = fixed inset-0 z-40 div
    const overlay = container.querySelector('div.fixed.inset-0.z-40')!;
    fireEvent.click(overlay);
    expect(mobileAside().className).toContain('-translate-x-full');
  });

  it('UploadBar-Gate: show_bottom_upload=false versteckt die Bar', async () => {
    getStatusBarStateMock.mockResolvedValue({ pills: [], show_bottom_upload: false });
    renderLayout();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId('upload-progress-bar')).not.toBeInTheDocument(),
    );
  });

  it('UploadBar-Gate: Fetch-Fehler lässt die Bar sichtbar (Default true)', async () => {
    getStatusBarStateMock.mockRejectedValue(new Error('boom'));
    renderLayout();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    expect(screen.getByTestId('upload-progress-bar')).toBeInTheDocument();
  });

  it('Standard-Mode: PowerMenu, UserMenu, NotificationCenter, StatusStrip im Header', () => {
    renderLayout();
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
    expect(screen.getByTestId('user-menu')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByTestId('topbar-status-strip')).toBeInTheDocument();
  });
});
