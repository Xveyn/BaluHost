import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
// stub children so this test targets ONLY the sidebar's branching/guards
vi.mock('../../../../components/plugins/plugin-management/PluginDetailsCard', () => ({ PluginDetailsCard: () => <div data-testid="details" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginPermissionsCard', () => ({ PluginPermissionsCard: () => <div data-testid="perms" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginDashboardPanelCard', () => ({ PluginDashboardPanelCard: () => <div data-testid="panel" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginActionsCard', () => ({ PluginActionsCard: () => <div data-testid="actions" /> }));
vi.mock('../../../../components/plugins/PluginSettingsSection', () => ({ PluginSettingsSection: () => <div data-testid="settings" /> }));
import { PluginDetailsSidebar } from '../../../../components/plugins/plugin-management/PluginDetailsSidebar';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});
const noop = () => {};
const props = { detailsLoading: false, actionLoading: false, onToggleDashboardPanel: noop, onConfigure: noop, onUninstall: noop };

describe('PluginDetailsSidebar', () => {
  it('shows the empty prompt when no plugin is selected', () => {
    render(<PluginDetailsSidebar plugin={null} {...props} />);
    expect(screen.getByText('empty.selectPlugin')).toBeInTheDocument();
    expect(screen.queryByTestId('details')).not.toBeInTheDocument();
  });

  it('renders details + permissions + actions for a selected plugin', () => {
    render(<PluginDetailsSidebar plugin={detail()} {...props} />);
    expect(screen.getByTestId('details')).toBeInTheDocument();
    expect(screen.getByTestId('perms')).toBeInTheDocument();
    expect(screen.getByTestId('actions')).toBeInTheDocument();
  });

  it('renders the dashboard-panel card only when has_dashboard_panel && is_enabled', () => {
    const { rerender } = render(<PluginDetailsSidebar plugin={detail({ has_dashboard_panel: true, is_enabled: true })} {...props} />);
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    rerender(<PluginDetailsSidebar plugin={detail({ has_dashboard_panel: true, is_enabled: false })} {...props} />);
    expect(screen.queryByTestId('panel')).not.toBeInTheDocument();
  });

  it('renders the settings section only when config_schema && is_enabled', () => {
    const { rerender } = render(<PluginDetailsSidebar plugin={detail({ config_schema: { type: 'object' }, is_enabled: true })} {...props} />);
    expect(screen.getByTestId('settings')).toBeInTheDocument();
    rerender(<PluginDetailsSidebar plugin={detail({ config_schema: undefined, is_enabled: true })} {...props} />);
    expect(screen.queryByTestId('settings')).not.toBeInTheDocument();
  });
});
