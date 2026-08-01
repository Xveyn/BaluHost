/**
 * Render a component inside the providers the app actually mounts, with real
 * translations and a stubbed network.
 *
 * The problem this solves (T2/#316): page tests used to replace every provider
 * with a `vi.mock` block and then assert on i18n KEYS - `getByText('buttons.enable')`
 * passes just as happily when the translation is missing entirely. With a real
 * i18next instance the assertion becomes the text a user sees.
 *
 * Which providers are wrapped, and why not all of them:
 *
 *   always  ThemeProvider, QueryClientProvider, MemoryRouter, I18nextProvider,
 *           AuthProvider
 *           - all cheap: AuthProvider only reaches for /api/auth/me when a
 *             token is stored, which is what the `auth` option does. Mounting
 *             it unconditionally means a component using useAuth() just works
 *             instead of throwing "must be used within an AuthProvider".
 *   opt-in  PluginProvider (`withPlugins`)
 *           - fetches the plugin list AND the UI manifest as soon as a user is
 *             signed in, so a test that does not need it should not have to
 *             stub two more routes
 *   never   NotificationProvider, UploadProvider
 *           - they open a WebSocket and hold upload state. Add them here when
 *             a test needs one, together with the fake that makes it safe.
 *
 * The network comes from ONE route table for both transports - see apiStub.ts;
 * AuthProvider talks raw `fetch`, everything else goes through axios.
 */
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';

import { AuthProvider } from '../../contexts/AuthContext';
import { PluginProvider } from '../../contexts/PluginContext';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { createTestQueryClient } from './queryClient';
import { createTestI18n } from './i18nTest';
import { installApiStub, type ApiRoutes, type ApiStub } from './apiStub';

export interface TestUser {
  id?: number;
  username?: string;
  role?: 'admin' | 'user';
  [key: string]: unknown;
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Initial URL for the MemoryRouter. */
  route?: string;
  language?: 'de' | 'en';
  queryClient?: QueryClient;
  /** Route table for both axios and fetch — see apiStub.ts. */
  api?: ApiRoutes;
  /**
   * Mount AuthProvider with this user already signed in. Seeds the token in
   * localStorage and answers /api/auth/me, which is what the provider asks for
   * on mount.
   */
  auth?: TestUser | false;
  /** Mount PluginProvider (needs `auth`, it only loads with a token). */
  withPlugins?: boolean;
}

export interface RenderWithProvidersResult extends RenderResult {
  user: ReturnType<typeof userEvent.setup>;
  api: ApiStub;
}

const ADMIN: Required<Pick<TestUser, 'id' | 'username' | 'role'>> = {
  id: 1,
  username: 'admin',
  role: 'admin',
};

let activeStub: ApiStub | null = null;

afterEach(() => {
  activeStub?.restore();
  activeStub = null;
  localStorage.clear();
});

export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const {
    route = '/',
    language = 'de',
    queryClient = createTestQueryClient(),
    api = {},
    auth = false,
    withPlugins = false,
    ...renderOptions
  } = options;

  const user = auth === false ? null : { ...ADMIN, ...auth };
  if (user) {
    localStorage.setItem('token', 'test-token');
  }

  // The caller's routes win: a test that wants /api/auth/me to fail says so.
  const routes: ApiRoutes = user
    ? { '/api/auth/me': { user }, ...api }
    : api;

  activeStub?.restore();
  const stub = installApiStub(routes);
  activeStub = stub;

  const i18nInstance = createTestI18n(language);

  function Wrapper({ children }: { children: ReactNode }) {
    let tree = <>{children}</>;
    if (withPlugins) tree = <PluginProvider>{tree}</PluginProvider>;
    tree = <AuthProvider>{tree}</AuthProvider>;
    return (
      <MemoryRouter initialEntries={[route]}>
        <I18nextProvider i18n={i18nInstance}>
          <ThemeProvider>
            <QueryClientProvider client={queryClient}>{tree}</QueryClientProvider>
          </ThemeProvider>
        </I18nextProvider>
      </MemoryRouter>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    user: userEvent.setup(),
    api: stub,
  };
}
