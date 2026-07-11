import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginInfo, PluginDetail } from '../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const hookValue = {
  plugins: [] as PluginInfo[], isLoading: false, error: null, refreshPlugins: vi.fn(),
  allPermissions: [], scopeCatalog: [], selectedPlugin: null as PluginDetail | null,
  detailsLoading: false, actionLoading: false, actionError: null,
  loadPluginDetails: vi.fn(), handleTogglePlugin: vi.fn(), handleEnableWithPermissions: vi.fn(),
  handleEnableWithScopes: vi.fn(), handleUninstall: vi.fn(), handleToggleDashboardPanel: vi.fn(),
  showPermissionModal: false, setShowPermissionModal: vi.fn(), selectedPermissions: [], togglePermission: vi.fn(),
  showScopeModal: false, setShowScopeModal: vi.fn(), selectedScopes: [], toggleScope: vi.fn(),
  dialog: null,
};
vi.mock('../../hooks/usePluginManagement', () => ({ usePluginManagement: () => hookValue }));
vi.mock('../../components/plugins/MarketplaceTab', () => ({ default: () => <div data-testid="marketplace" /> }));
vi.mock('../../components/plugins/PluginDocumentation', () => ({ default: () => <div data-testid="docs" /> }));
// real plugin-management barrel components render (already unit-tested); make the
// plugin-name resolver deterministic so PluginListCard shows the raw display_name
vi.mock('../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));

import PluginsPage from '../../pages/PluginsPage';

describe('PluginsPage', () => {
  beforeEach(() => { hookValue.plugins = []; hookValue.selectedPlugin = null; });

  it('shows the empty-state on the plugins tab when there are no plugins', () => {
    render(<PluginsPage />);
    expect(screen.getByText('empty.noPlugins')).toBeInTheDocument();
    // sidebar empty prompt is also present
    expect(screen.getByText('empty.selectPlugin')).toBeInTheDocument();
  });

  it('renders the plugin list when plugins exist', () => {
    hookValue.plugins = [{
      name: 'demo', version: '1', display_name: 'Demo Plugin', description: '', author: '',
      category: 'general', required_permissions: [], dangerous_permissions: [],
      is_enabled: false, has_ui: false, has_routes: false,
    }];
    render(<PluginsPage />);
    expect(screen.getByText('Demo Plugin')).toBeInTheDocument();
    expect(screen.queryByText('empty.noPlugins')).not.toBeInTheDocument();
  });
});
