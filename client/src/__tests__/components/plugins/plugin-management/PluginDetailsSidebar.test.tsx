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
import deLocaleJson from '../../../../i18n/locales/de/plugins.json';
import enLocaleJson from '../../../../i18n/locales/en/plugins.json';

type NoticeTexts = { restartRequired?: { title?: unknown; description?: unknown } };
const deLocale = deLocaleJson as NoticeTexts;
const enLocale = enLocaleJson as NoticeTexts;

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

  // #619: a router plugin enabled at runtime has no endpoints until the backend
  // restarts. Without this notice its topbar entry looks ready and 404s.
  describe('restart-required notice', () => {
    it('shows the notice for an enabled plugin whose routes are not mounted yet', () => {
      render(<PluginDetailsSidebar plugin={detail({ is_enabled: true, restart_required: true })} {...props} />);
      expect(screen.getByRole('alert')).toHaveTextContent('restartRequired.title');
      expect(screen.getByRole('alert')).toHaveTextContent('restartRequired.description');
    });

    it('hides the notice for a disabled plugin even though the backend reports restart_required', () => {
      // router_restart_required() does not look at enablement: a router plugin
      // that was off at startup reports true while it is still off.
      render(<PluginDetailsSidebar plugin={detail({ is_enabled: false, restart_required: true })} {...props} />);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('hides the notice when the routes are mounted', () => {
      render(<PluginDetailsSidebar plugin={detail({ is_enabled: true, restart_required: false })} {...props} />);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('hides the notice when an older backend omits the field', () => {
      render(<PluginDetailsSidebar plugin={detail({ is_enabled: true })} {...props} />);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    // The t() mock above echoes keys, so a missing locale entry would pass
    // every render test. Check the real files instead.
    it.each([
      ['de', deLocale],
      ['en', enLocale],
    ])('has both notice texts in the %s locale', (_lang, locale) => {
      expect(locale.restartRequired?.title).toEqual(expect.any(String));
      expect(locale.restartRequired?.description).toEqual(expect.any(String));
    });
  });
});
