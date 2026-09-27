import { useTranslation } from 'react-i18next';
import { AlertTriangle, Settings } from 'lucide-react';
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
          {/* restart_required alone is also true for a disabled router plugin
              (#619) - the notice only applies once it is switched on. */}
          {plugin.is_enabled && plugin.restart_required && (
            <div
              role="alert"
              className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4"
            >
              <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-400" aria-hidden="true" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-amber-200">{t('restartRequired.title')}</p>
                <p className="text-sm text-amber-100/80">{t('restartRequired.description')}</p>
              </div>
            </div>
          )}
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
