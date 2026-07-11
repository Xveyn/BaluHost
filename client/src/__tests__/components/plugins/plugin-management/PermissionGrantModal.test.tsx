import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail, PermissionInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PermissionGrantModal } from '../../../../components/plugins/plugin-management/PermissionGrantModal';

const plugin: PluginDetail = {
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: ['files.read', 'files.write'], granted_permissions: [],
  dangerous_permissions: ['files.write'], is_enabled: false, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {},
};
const perms: PermissionInfo[] = [
  { name: 'r', value: 'files.read', dangerous: false, description: 'read' },
  { name: 'w', value: 'files.write', dangerous: true, description: 'write' },
];

describe('PermissionGrantModal', () => {
  it('disables the enable button until every required permission is selected', () => {
    const { rerender } = render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={() => {}} />,
    );
    expect(screen.getByText('buttons.enablePlugin').closest('button')).toBeDisabled();
    rerender(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read', 'files.write']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={() => {}} />,
    );
    expect(screen.getByText('buttons.enablePlugin').closest('button')).not.toBeDisabled();
  });

  it('fires onTogglePermission with the permission when a checkbox changes', () => {
    const onToggle = vi.fn();
    render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={[]}
        onTogglePermission={onToggle} onCancel={() => {}} onConfirm={() => {}} />,
    );
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onToggle).toHaveBeenCalledWith('files.read');
  });

  it('fires onConfirm when the (enabled) enable button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read', 'files.write']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByText('buttons.enablePlugin'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
