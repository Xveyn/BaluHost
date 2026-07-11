import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { usePlugins } from '../contexts/PluginContext';
import type {
  PluginDetail,
  PluginInfo,
  PermissionInfo,
  ScopeInfo,
} from '../api/plugins';
import {
  getPluginDetails,
  getScopeCatalog,
  listPermissions,
  togglePlugin,
  toggleDashboardPanel,
  uninstallPlugin,
} from '../api/plugins';
import { useConfirmDialog } from './useConfirmDialog';
import type { ReactNode } from 'react';

export interface UsePluginManagementResult {
  plugins: PluginInfo[];
  isLoading: boolean;
  error: string | null;
  refreshPlugins: () => Promise<void>;
  allPermissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];
  selectedPlugin: PluginDetail | null;
  detailsLoading: boolean;
  actionLoading: boolean;
  actionError: string | null;
  loadPluginDetails: (name: string) => Promise<PluginDetail | null>;
  handleTogglePlugin: (plugin: PluginInfo) => Promise<void>;
  handleEnableWithPermissions: () => Promise<void>;
  handleEnableWithScopes: () => Promise<void>;
  handleUninstall: (name: string) => Promise<void>;
  handleToggleDashboardPanel: () => Promise<void>;
  showPermissionModal: boolean;
  setShowPermissionModal: (v: boolean) => void;
  selectedPermissions: string[];
  togglePermission: (perm: string) => void;
  showScopeModal: boolean;
  setShowScopeModal: (v: boolean) => void;
  selectedScopes: string[];
  toggleScope: (scope: string) => void;
  dialog: ReactNode;
}

export function usePluginManagement(): UsePluginManagementResult {
  const { t } = useTranslation(['plugins', 'common']);
  const { confirm, dialog } = useConfirmDialog();
  const { plugins, isLoading, error, refreshPlugins } = usePlugins();
  const [selectedPlugin, setSelectedPlugin] = useState<PluginDetail | null>(null);
  const [allPermissions, setAllPermissions] = useState<PermissionInfo[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showPermissionModal, setShowPermissionModal] = useState(false);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [scopeCatalog, setScopeCatalog] = useState<ScopeInfo[]>([]);
  const [showScopeModal, setShowScopeModal] = useState(false);
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);

  // Load all permissions on mount
  useEffect(() => {
    listPermissions()
      .then((res) => setAllPermissions(res.permissions))
      .catch(console.error);
  }, []);

  // Load scope catalog on mount (for external plugin scope-picker)
  useEffect(() => {
    getScopeCatalog()
      .then((res) => setScopeCatalog(res.scopes))
      .catch(console.error);
  }, []);

  const loadPluginDetails = async (name: string): Promise<PluginDetail | null> => {
    setDetailsLoading(true);
    setActionError(null);
    try {
      const details = await getPluginDetails(name);
      setSelectedPlugin(details);
      return details;
    } catch {
      setActionError(t('errors.loadDetailsFailed'));
      return null;
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleTogglePlugin = async (plugin: PluginInfo) => {
    if (plugin.is_enabled) {
      // Disable plugin
      setActionLoading(true);
      setActionError(null);
      try {
        await togglePlugin(plugin.name, { enabled: false });
        await refreshPlugins();
        if (selectedPlugin?.name === plugin.name) {
          await loadPluginDetails(plugin.name);
        }
      } catch {
        setActionError(t('errors.disableFailed'));
      } finally {
        setActionLoading(false);
      }
    } else {
      // Enable: load details to learn tier + requested scopes
      const details = await loadPluginDetails(plugin.name);
      if (!details) return;
      if (details.is_external) {
        setSelectedScopes(
          (details.requested_api_scopes ?? []).filter((s) =>
            scopeCatalog.some((c) => c.key === s),
          ),
        );
        setShowScopeModal(true);
      } else {
        setSelectedPermissions(plugin.required_permissions);
        setShowPermissionModal(true);
      }
    }
  };

  const handleEnableWithPermissions = async () => {
    if (!selectedPlugin) return;

    setActionLoading(true);
    setActionError(null);
    setShowPermissionModal(false);

    try {
      await togglePlugin(selectedPlugin.name, {
        enabled: true,
        grant_permissions: selectedPermissions,
      });
      await refreshPlugins();
      await loadPluginDetails(selectedPlugin.name);
    } catch {
      setActionError(t('errors.enableFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleEnableWithScopes = async () => {
    if (!selectedPlugin) return;
    setActionLoading(true);
    setActionError(null);
    setShowScopeModal(false);
    try {
      await togglePlugin(selectedPlugin.name, {
        enabled: true,
        grant_api_scopes: selectedScopes,
      });
      await refreshPlugins();
      await loadPluginDetails(selectedPlugin.name);
    } catch {
      setActionError(t('errors.enableFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleUninstall = async (name: string) => {
    const ok = await confirm(t('confirm.uninstall', { name }), { title: t('buttons.uninstall'), variant: 'danger', confirmLabel: t('buttons.uninstall') });
    if (!ok) return;

    setActionLoading(true);
    setActionError(null);
    try {
      await uninstallPlugin(name);
      await refreshPlugins();
      if (selectedPlugin?.name === name) {
        setSelectedPlugin(null);
      }
    } catch {
      setActionError(t('errors.uninstallFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleDashboardPanel = async () => {
    if (!selectedPlugin) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await toggleDashboardPanel(selectedPlugin.name, !selectedPlugin.dashboard_panel_enabled);
      await loadPluginDetails(selectedPlugin.name);
    } catch {
      setActionError(t('dashboardPanel.enableFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const togglePermission = (perm: string) => {
    setSelectedPermissions((prev) =>
      prev.includes(perm) ? prev.filter((p) => p !== perm) : [...prev, perm],
    );
  };

  const toggleScope = (scope: string) => {
    setSelectedScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  return {
    plugins,
    isLoading,
    error,
    refreshPlugins,
    allPermissions,
    scopeCatalog,
    selectedPlugin,
    detailsLoading,
    actionLoading,
    actionError,
    loadPluginDetails,
    handleTogglePlugin,
    handleEnableWithPermissions,
    handleEnableWithScopes,
    handleUninstall,
    handleToggleDashboardPanel,
    showPermissionModal,
    setShowPermissionModal,
    selectedPermissions,
    togglePermission,
    showScopeModal,
    setShowScopeModal,
    selectedScopes,
    toggleScope,
    dialog,
  };
}
