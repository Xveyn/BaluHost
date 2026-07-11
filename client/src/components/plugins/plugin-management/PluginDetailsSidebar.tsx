import { useTranslation } from 'react-i18next';
import { Settings } from 'lucide-react';
import type { PluginDetail } from '../../../api/plugins';
import { PluginDetailsCard } from './PluginDetailsCard';
import { PluginPermissionsCard } from './PluginPermissionsCard';
import { PluginDashboardPanelCard } from './PluginDashboardPanelCard';
import { PluginActionsCard } from './PluginActionsCard';
import { PluginSettingsSection } from '../PluginSettingsSection';

export function PluginDetailsSidebar({
  plugin,
  detailsLoading,
  actionLoading,
  onToggleDashboardPanel,
  onConfigure,
  onUninstall,
}: {
  plugin: PluginDetail | null;
  detailsLoading: boolean;
  actionLoading: boolean;
  onToggleDashboardPanel: () => void;
  onConfigure: () => void;
  onUninstall: (name: string) => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="space-y-4">
      {detailsLoading ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-6 bg-slate-800 rounded w-3/4" />
            <div className="h-4 bg-slate-800 rounded w-1/2" />
            <div className="h-20 bg-slate-800 rounded" />
          </div>
        </div>
      ) : plugin ? (
        <>
          <PluginDetailsCard plugin={plugin} />
          <PluginPermissionsCard plugin={plugin} />
          {plugin.has_dashboard_panel && plugin.is_enabled && (
            <PluginDashboardPanelCard
              plugin={plugin}
              actionLoading={actionLoading}
              onToggle={onToggleDashboardPanel}
            />
          )}
          {plugin?.config_schema && plugin.is_enabled && (
            <PluginSettingsSection
              pluginName={plugin.name}
              configSchema={plugin.config_schema}
              config={plugin.config ?? {}}
              translations={plugin.translations ?? undefined}
            />
          )}
          <PluginActionsCard
            plugin={plugin}
            actionLoading={actionLoading}
            onConfigure={onConfigure}
            onUninstall={onUninstall}
          />
        </>
      ) : (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center">
          <Settings className="h-8 w-8 mx-auto text-slate-600 mb-3" />
          <p className="text-sm text-slate-500">
            {t('empty.selectPlugin')}
          </p>
        </div>
      )}
    </div>
  );
}
