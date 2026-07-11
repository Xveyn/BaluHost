import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { PluginInfo, PluginDetail, ScopeInfo } from '../../api/plugins';

const mockRefreshPlugins = vi.fn().mockResolvedValue(undefined);
vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({
    plugins: [] as PluginInfo[],
    isLoading: false,
    error: null,
    refreshPlugins: mockRefreshPlugins,
  }),
}));

const mockConfirm = vi.fn();
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm, dialog: null }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

vi.mock('../../api/plugins', () => ({
  getPluginDetails: vi.fn(),
  getScopeCatalog: vi.fn().mockResolvedValue({ scopes: [] }),
  listPermissions: vi.fn().mockResolvedValue({ permissions: [] }),
  togglePlugin: vi.fn().mockResolvedValue({}),
  toggleDashboardPanel: vi.fn().mockResolvedValue({}),
  uninstallPlugin: vi.fn().mockResolvedValue({}),
}));

import { usePluginManagement } from '../../hooks/usePluginManagement';
import * as api from '../../api/plugins';

const internalPlugin: PluginInfo = {
  name: 'demo', version: '1.0.0', display_name: 'Demo', description: 'd',
  author: 'a', category: 'general', required_permissions: ['files.read'],
  dangerous_permissions: [], is_enabled: false, has_ui: false, has_routes: false,
};

function detail(over: Partial<PluginDetail> = {}): PluginDetail {
  return {
    name: 'demo', version: '1.0.0', display_name: 'Demo', description: 'd', author: 'a',
    category: 'general', dependencies: [], required_permissions: ['files.read'],
    granted_permissions: [], dangerous_permissions: [], is_enabled: false,
    is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
    has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [],
    dashboard_widgets: [], config: {}, ...over,
  };
}

describe('usePluginManagement', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sets actionError when loadPluginDetails fails and returns null', async () => {
    vi.mocked(api.getPluginDetails).mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => usePluginManagement());
    let ret: PluginDetail | null = detail();
    await act(async () => { ret = await result.current.loadPluginDetails('demo'); });
    expect(ret).toBeNull();
    expect(result.current.actionError).toBe('errors.loadDetailsFailed');
  });

  it('opens the permission modal (not the scope modal) when enabling an internal plugin', async () => {
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(detail({ is_external: false }));
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleTogglePlugin(internalPlugin); });
    expect(result.current.showPermissionModal).toBe(true);
    expect(result.current.showScopeModal).toBe(false);
    expect(result.current.selectedPermissions).toEqual(['files.read']);
  });

  it('opens the scope modal seeded with catalog-filtered requested scopes for an external plugin', async () => {
    const catalog: ScopeInfo[] = [{ key: 'ui.read', tier: 'frontend', dangerous: false }];
    vi.mocked(api.getScopeCatalog).mockResolvedValue({ scopes: catalog });
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(
      detail({ is_external: true, requested_api_scopes: ['ui.read', 'not.in.catalog'] }),
    );
    const { result } = renderHook(() => usePluginManagement());
    await waitFor(() => expect(result.current.scopeCatalog).toHaveLength(1));
    await act(async () => { await result.current.handleTogglePlugin({ ...internalPlugin, is_external: true }); });
    expect(result.current.showScopeModal).toBe(true);
    expect(result.current.showPermissionModal).toBe(false);
    expect(result.current.selectedScopes).toEqual(['ui.read']); // 'not.in.catalog' filtered out
  });

  it('does not call uninstallPlugin when the confirm dialog is declined', async () => {
    mockConfirm.mockResolvedValueOnce(false);
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleUninstall('demo'); });
    expect(api.uninstallPlugin).not.toHaveBeenCalled();
  });

  it('calls uninstallPlugin and refreshes when the confirm dialog is accepted', async () => {
    mockConfirm.mockResolvedValueOnce(true);
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleUninstall('demo'); });
    expect(api.uninstallPlugin).toHaveBeenCalledWith('demo');
    expect(mockRefreshPlugins).toHaveBeenCalled();
  });

  it('togglePermission adds then removes a permission', () => {
    const { result } = renderHook(() => usePluginManagement());
    act(() => result.current.togglePermission('files.write'));
    expect(result.current.selectedPermissions).toContain('files.write');
    act(() => result.current.togglePermission('files.write'));
    expect(result.current.selectedPermissions).not.toContain('files.write');
  });

  it('handleEnableWithPermissions posts enabled:true + grant_permissions from the selection', async () => {
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(detail({ is_external: false }));
    const { result } = renderHook(() => usePluginManagement());
    // seed selectedPlugin + selectedPermissions via the internal-enable branch
    await act(async () => { await result.current.handleTogglePlugin(internalPlugin); });
    await act(async () => { await result.current.handleEnableWithPermissions(); });
    expect(api.togglePlugin).toHaveBeenCalledWith('demo', { enabled: true, grant_permissions: ['files.read'] });
    expect(result.current.showPermissionModal).toBe(false);
  });

  it('handleEnableWithScopes posts enabled:true + grant_api_scopes from the catalog-filtered selection', async () => {
    const catalog: ScopeInfo[] = [{ key: 'ui.read', tier: 'frontend', dangerous: false }];
    vi.mocked(api.getScopeCatalog).mockResolvedValue({ scopes: catalog });
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(
      detail({ is_external: true, requested_api_scopes: ['ui.read', 'not.in.catalog'] }),
    );
    const { result } = renderHook(() => usePluginManagement());
    await waitFor(() => expect(result.current.scopeCatalog).toHaveLength(1));
    await act(async () => { await result.current.handleTogglePlugin({ ...internalPlugin, is_external: true }); });
    await act(async () => { await result.current.handleEnableWithScopes(); });
    expect(api.togglePlugin).toHaveBeenCalledWith('demo', { enabled: true, grant_api_scopes: ['ui.read'] });
    expect(result.current.showScopeModal).toBe(false);
  });
});
