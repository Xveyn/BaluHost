import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../components/LocalOnlyAction', () => ({ LocalOnlyAction: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
import { PluginActionsCard } from '../../../../components/plugins/plugin-management/PluginActionsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginActionsCard', () => {
  it('disables the uninstall button while the plugin is enabled', () => {
    render(<PluginActionsCard plugin={detail({ is_enabled: true })} actionLoading={false} onConfigure={() => {}} onUninstall={() => {}} />);
    expect(screen.getByText('buttons.uninstall').closest('button')).toBeDisabled();
  });

  it('fires onUninstall with the plugin name when enabled=false and clicked', () => {
    const onUninstall = vi.fn();
    render(<PluginActionsCard plugin={detail({ is_enabled: false })} actionLoading={false} onConfigure={() => {}} onUninstall={onUninstall} />);
    fireEvent.click(screen.getByText('buttons.uninstall'));
    expect(onUninstall).toHaveBeenCalledWith('demo');
  });

  it('fires onConfigure when configure is clicked', () => {
    const onConfigure = vi.fn();
    render(<PluginActionsCard plugin={detail()} actionLoading={false} onConfigure={onConfigure} onUninstall={() => {}} />);
    fireEvent.click(screen.getByText('buttons.configure'));
    expect(onConfigure).toHaveBeenCalledTimes(1);
  });
});
