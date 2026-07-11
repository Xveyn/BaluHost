import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginDashboardPanelCard } from '../../../../components/plugins/plugin-management/PluginDashboardPanelCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: true, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginDashboardPanelCard', () => {
  it('shows the enable-panel label + inactive state when the panel is off', () => {
    render(<PluginDashboardPanelCard plugin={detail({ dashboard_panel_enabled: false })} actionLoading={false} onToggle={() => {}} />);
    expect(screen.getByText('buttons.enablePanel')).toBeInTheDocument();
    expect(screen.getByText('dashboardPanel.inactive')).toBeInTheDocument();
  });

  it('fires onToggle when the button is clicked', () => {
    const onToggle = vi.fn();
    render(<PluginDashboardPanelCard plugin={detail({ dashboard_panel_enabled: true })} actionLoading={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('buttons.disablePanel'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
