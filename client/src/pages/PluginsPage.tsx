/**
 * Plugin Management Page
 *
 * Admin-only page for managing installed plugins.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import PluginDocumentation from '../components/plugins/PluginDocumentation';
import MarketplaceTab from '../components/plugins/MarketplaceTab';
import { usePluginManagement } from '../hooks/usePluginManagement';
import type { TabType } from '../components/plugins/plugin-management';
import {
  PluginTabNav,
  PluginList,
  PluginDetailsSidebar,
  PermissionGrantModal,
  ScopeGrantModal,
} from '../components/plugins/plugin-management';

export default function PluginsPage() {
  const { t } = useTranslation(['plugins', 'common']);
  const [activeTab, setActiveTab] = useState<TabType>('plugins');
  const {
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
  } = usePluginManagement();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {t('description')}
          </p>
        </div>
        {activeTab === 'plugins' && (
          <button
            onClick={refreshPlugins}
            className="rounded-lg px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40"
          >
            {t('buttons.refresh')}
          </button>
        )}
      </div>

      {/* Tab Navigation */}
      <PluginTabNav activeTab={activeTab} onSelect={setActiveTab} />

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400">
          {error}
        </div>
      )}

      {activeTab === 'plugins' && actionError && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          {actionError}
        </div>
      )}

      {/* Marketplace Tab */}
      {activeTab === 'marketplace' && <MarketplaceTab />}

      {/* Documentation Tab */}
      {activeTab === 'documentation' && (
        <PluginDocumentation permissions={allPermissions} scopeCatalog={scopeCatalog} />
      )}

      {/* Plugins Tab */}
      {activeTab === 'plugins' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <PluginList
            plugins={plugins}
            selectedName={selectedPlugin?.name ?? null}
            actionLoading={actionLoading}
            onSelect={loadPluginDetails}
            onToggle={handleTogglePlugin}
          />
          <PluginDetailsSidebar
            plugin={selectedPlugin}
            detailsLoading={detailsLoading}
            actionLoading={actionLoading}
            onToggleDashboardPanel={handleToggleDashboardPanel}
            onConfigure={() => setShowPermissionModal(true)}
            onUninstall={handleUninstall}
          />
        </div>
      )}

      {/* Permission Grant Modal */}
      {showPermissionModal && selectedPlugin && (
        <PermissionGrantModal
          plugin={selectedPlugin}
          allPermissions={allPermissions}
          selectedPermissions={selectedPermissions}
          onTogglePermission={togglePermission}
          onCancel={() => setShowPermissionModal(false)}
          onConfirm={handleEnableWithPermissions}
        />
      )}

      {/* Scope Grant Modal (external plugins only) */}
      {showScopeModal && selectedPlugin && (
        <ScopeGrantModal
          plugin={selectedPlugin}
          scopeCatalog={scopeCatalog}
          selectedScopes={selectedScopes}
          onToggleScope={toggleScope}
          onCancel={() => setShowScopeModal(false)}
          onConfirm={handleEnableWithScopes}
        />
      )}

      {dialog}
    </div>
  );
}
