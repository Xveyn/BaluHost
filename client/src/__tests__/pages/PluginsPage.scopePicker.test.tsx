/**
 * Scope-picker (external plugins) vs permissions modal (bundled ones).
 *
 * This file was T2/#316's exhibit: ten vi.mock blocks and assertions against
 * i18n KEYS, which pass just as happily when a translation is missing. It now
 * runs on renderWithProviders — real i18next, real PluginProvider, real
 * api/plugins module — so the assertions are the German text a user sees and
 * the toggle assertion is the request body that actually goes out.
 *
 * Four mocks remain, and they are a different kind: heavy children that this
 * test is not about (documentation pane, settings section, marketplace tab,
 * the local-network gate). No render helper removes those; keeping them is a
 * scoping decision, not missing infrastructure.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import PluginsPage from '../../pages/PluginsPage';
import { renderWithProviders } from '../helpers/renderWithProviders';

vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn(), dialog: null }),
}));
vi.mock('../../components/plugins/PluginDocumentation', () => ({ default: () => null }));
vi.mock('../../components/plugins/PluginSettingsSection', () => ({ PluginSettingsSection: () => null }));
vi.mock('../../components/plugins/MarketplaceTab', () => ({ default: () => null }));
vi.mock('../../components/LocalOnlyAction', () => ({
  LocalOnlyAction: ({ children }: { children: React.ReactNode }) => children,
}));

const CATALOG = {
  scopes: [
    { key: 'read:system-info', tier: 'frontend', dangerous: false },
    { key: 'read:storage', tier: 'frontend', dangerous: false },
    { key: 'read:power', tier: 'frontend', dangerous: false },
    { key: 'storage', tier: 'backend', dangerous: false },
    { key: 'core.system_metrics', tier: 'backend', dangerous: false },
    { key: 'core.notify', tier: 'backend', dangerous: false },
  ],
};

function makePlugin(over: Record<string, unknown> = {}) {
  return {
    name: 'weather', version: '2.0.0', display_name: 'Weather', description: 'd',
    author: 'a', category: 'general', required_permissions: [], dangerous_permissions: [],
    is_enabled: false, has_ui: true, has_routes: true, is_external: true, ...over,
  };
}

/** Everything PluginsPage and the providers around it ask for. */
function routesFor(listed: Record<string, unknown>, details: Record<string, unknown>) {
  return {
    '/api/plugins': { plugins: [listed] },
    '/api/plugins/ui/manifest': { plugins: [] },
    '/api/plugins/scope-catalog': CATALOG,
    '/api/plugins/permissions': { permissions: [] },
    '/api/plugins/weather': details,
    'POST /api/plugins/weather/toggle': { name: 'weather', is_enabled: true, message: 'ok' },
  };
}

describe('PluginsPage scope-picker (external) vs permissions modal (bundled)', () => {
  it('external: pre-checks requested scopes, sends the checked subset', async () => {
    const { user, api } = renderWithProviders(<PluginsPage />, {
      auth: { username: 'admin', role: 'admin' },
      withPlugins: true,
      api: routesFor(
        makePlugin(),
        makePlugin({
          is_installed: false,
          requested_api_scopes: ['storage', 'read:power'],
          dashboard_panel_enabled: false,
        }),
      ),
    });

    // The picker computes its pre-selection from the catalog at click time.
    await waitFor(() => expect(api.callsTo('/api/plugins/scope-catalog')).toHaveLength(1));

    await user.click(await screen.findByText('Aktivieren'));

    expect(await screen.findByText(/Capability-Scopes gewähren/)).toBeInTheDocument();

    // The label a user actually sees for the backend scope. Real i18n makes
    // this assertion meaningful: with the old mocked `t` it read "storage".
    expect(screen.getByRole('checkbox', { name: /Plugin-Speicher/ })).toBeChecked();
    // The frontend scope, whose key contains a colon. This assertion is the
    // regression guard for the nsSeparator bug the migration uncovered:
    // without `nsSeparator: false` in ScopeGrantModal the label falls back to
    // the raw key "read:power" and the description disappears entirely.
    expect(screen.getByRole('checkbox', { name: /Energieinfo/ })).toBeChecked();

    await user.click(screen.getByRole('checkbox', { name: /Energieinfo/ }));
    await user.click(screen.getByText('Gewähren & Aktivieren'));

    // Asserted on the request that leaves the app, not on a mocked function.
    await waitFor(() => expect(api.callsTo('/api/plugins/weather/toggle', 'POST')).toHaveLength(1));
    expect(api.callsTo('/api/plugins/weather/toggle', 'POST')[0].body).toEqual({
      enabled: true,
      grant_api_scopes: ['storage'],
    });
  });

  it('bundled: shows the permissions modal, not the scope-picker', async () => {
    const bundled = { is_external: false, required_permissions: ['file:read'] };
    const { user } = renderWithProviders(<PluginsPage />, {
      auth: { username: 'admin', role: 'admin' },
      withPlugins: true,
      api: routesFor(
        makePlugin(bundled),
        makePlugin({ ...bundled, dangerous_permissions: [], granted_permissions: [] }),
      ),
    });

    await user.click(await screen.findByText('Aktivieren'));

    expect(await screen.findByText('Dieses Plugin benötigt folgende Berechtigungen:')).toBeInTheDocument();
    expect(screen.queryByText(/Capability-Scopes gewähren/)).not.toBeInTheDocument();
  });
});
