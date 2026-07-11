import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginPermissionsCard } from '../../../../components/plugins/plugin-management/PluginPermissionsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '',
  category: 'general', dependencies: [], required_permissions: [], granted_permissions: [],
  dangerous_permissions: [], is_enabled: true, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginPermissionsCard', () => {
  it('shows the noPermissions text when there are none', () => {
    render(<PluginPermissionsCard plugin={detail()} />);
    expect(screen.getByText('permissions.noPermissions')).toBeInTheDocument();
  });

  it('lists each required permission', () => {
    render(<PluginPermissionsCard plugin={detail({ required_permissions: ['files.read', 'files.write'], granted_permissions: ['files.read'] })} />);
    expect(screen.getByText('files.read')).toBeInTheDocument();
    expect(screen.getByText('files.write')).toBeInTheDocument();
  });
});
