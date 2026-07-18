import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { lazy } from 'react';
import { AppLayout } from '../../components/layout/AppLayout';

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

// ---- Kontext-Mocks (gleiches Muster wie Layout.test.tsx) ----
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

// ---- Schwere Kinder mocken ----
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
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeEach(() => {
  authState.user = { id: 1, username: 'admin', role: 'admin' };
  authState.isAdmin = true;
  authState.isImpersonating = false;
  featureState.isPi = false;
  pluginState.pluginNavItems = [];
  getStatusBarStateMock.mockClear();
  getStatusBarStateMock.mockResolvedValue({ pills: [], show_bottom_upload: true });
});

describe('AppLayout (Suspense-Grenze liegt innerhalb von Layout)', () => {
  it('ein nie auflösender Seiten-Chunk zeigt den Fallback, während Sidebar/Header gemountet bleiben', async () => {
    // Never-resolving lazy import simulates an in-flight, slow page-chunk load —
    // the exact scenario the inner-Suspense placement is meant to improve on.
    const NeverResolves = lazy(
      () => new Promise<{ default: () => null }>(() => { /* never settles */ }),
    );

    render(
      <MemoryRouter initialEntries={['/x']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/x" element={<NeverResolves />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    // The inner Suspense's fallback (LoadingFallback) is showing...
    expect(await screen.findByText('Loading...')).toBeInTheDocument();
    // ...while Layout's own chrome — represented here by the always-present
    // UserMenu in the header — is still mounted and visible alongside it.
    // If the Suspense boundary instead wrapped Layout itself (the old
    // structure), this element would be gone too while the chunk is pending.
    expect(screen.getByTestId('user-menu')).toBeInTheDocument();
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
  });
});
