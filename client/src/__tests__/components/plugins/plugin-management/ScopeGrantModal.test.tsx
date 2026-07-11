import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail, ScopeInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { ScopeGrantModal } from '../../../../components/plugins/plugin-management/ScopeGrantModal';

const plugin = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: false, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [],
  config: {}, is_external: true, requested_api_scopes: ['ui.read', 'files.write'], ...over,
});
const catalog: ScopeInfo[] = [
  { key: 'ui.read', tier: 'frontend', dangerous: false },
  { key: 'files.write', tier: 'backend', dangerous: true },
];

describe('ScopeGrantModal', () => {
  it('renders both tier groups with one checkbox per requested+catalog scope', () => {
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={[]}
      onToggleScope={() => {}} onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText('scopeTiers.frontend')).toBeInTheDocument();
    expect(screen.getByText('scopeTiers.backend')).toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('shows the noScopes text when no requested scope is in the catalog', () => {
    render(<ScopeGrantModal plugin={plugin({ requested_api_scopes: ['unknown'] })} scopeCatalog={catalog}
      selectedScopes={[]} onToggleScope={() => {}} onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText('picker.noScopes')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('fires onToggleScope with the scope key on checkbox change', () => {
    const onToggleScope = vi.fn();
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={[]}
      onToggleScope={onToggleScope} onCancel={() => {}} onConfirm={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onToggleScope).toHaveBeenCalledWith('ui.read');
  });

  it('fires onConfirm when grant is clicked', () => {
    const onConfirm = vi.fn();
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={['ui.read']}
      onToggleScope={() => {}} onCancel={() => {}} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('picker.grant'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
