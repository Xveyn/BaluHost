import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PluginsPage from '../../pages/PluginsPage';
import { usePlugins } from '../../contexts/PluginContext';
import {
  getScopeCatalog, getPluginDetails, togglePlugin, listPermissions,
} from '../../api/plugins';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: vi.fn() }));
vi.mock('../../api/plugins', () => ({
  getScopeCatalog: vi.fn(),
  getPluginDetails: vi.fn(),
  togglePlugin: vi.fn().mockResolvedValue({ name: 'x', is_enabled: true, message: 'ok' }),
  listPermissions: vi.fn().mockResolvedValue({ permissions: [] }),
  toggleDashboardPanel: vi.fn(),
  uninstallPlugin: vi.fn(),
}));
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn(), dialog: null }),
}));
vi.mock('../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: unknown, f: string) => f }));
vi.mock('../../lib/safeUrl', () => ({ safeExternalUrl: () => null }));
vi.mock('../../components/plugins/PluginDocumentation', () => ({ default: () => null }));
vi.mock('../../components/plugins/PluginSettingsSection', () => ({ PluginSettingsSection: () => null }));
vi.mock('../../components/plugins/MarketplaceTab', () => ({ default: () => null }));
vi.mock('../../components/LocalOnlyAction', () => ({ LocalOnlyAction: ({ children }: { children: React.ReactNode }) => children }));

const mockUsePlugins = usePlugins as unknown as ReturnType<typeof vi.fn>;
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

beforeEach(() => {
  vi.clearAllMocks();
  (getScopeCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CATALOG);
});

describe('PluginsPage scope-picker (external) vs permissions modal (bundled)', () => {
  it('external: pre-checks requested scopes, sends the checked subset', async () => {
    mockUsePlugins.mockReturnValue({
      plugins: [makePlugin()], isLoading: false, error: null, refreshPlugins: vi.fn(),
    });
    (getPluginDetails as ReturnType<typeof vi.fn>).mockResolvedValue(
      makePlugin({ is_installed: false, requested_api_scopes: ['storage', 'read:power'], dashboard_panel_enabled: false }),
    );

    render(<PluginsPage />);
    // Wait until the catalog has loaded before opening the picker (avoids the
    // mount-effect race: selectedScopes is computed from scopeCatalog at click time).
    await waitFor(() => expect(getScopeCatalog).toHaveBeenCalled());

    fireEvent.click(await screen.findByText('buttons.enable'));

    expect(await screen.findByText('picker.title')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /storage/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /read:power/i })).toBeChecked();

    fireEvent.click(screen.getByRole('checkbox', { name: /read:power/i }));
    fireEvent.click(screen.getByText('picker.grant'));

    await waitFor(() =>
      expect(togglePlugin).toHaveBeenCalledWith('weather', {
        enabled: true,
        grant_api_scopes: ['storage'],
      }),
    );
  });

  it('bundled: shows the permissions modal, not the scope-picker', async () => {
    mockUsePlugins.mockReturnValue({
      plugins: [makePlugin({ is_external: false, required_permissions: ['file:read'] })],
      isLoading: false, error: null, refreshPlugins: vi.fn(),
    });
    (getPluginDetails as ReturnType<typeof vi.fn>).mockResolvedValue(
      makePlugin({ is_external: false, required_permissions: ['file:read'], dangerous_permissions: [], granted_permissions: [] }),
    );

    render(<PluginsPage />);
    fireEvent.click(await screen.findByText('buttons.enable'));

    expect(await screen.findByText('modal.enableDesc')).toBeInTheDocument();
    expect(screen.queryByText('picker.title')).not.toBeInTheDocument();
  });
});
