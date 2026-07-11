import { useTranslation } from 'react-i18next';
import { LayoutDashboard } from 'lucide-react';
import type { PluginDetail } from '../../../api/plugins';

export function PluginDashboardPanelCard({
  plugin,
  actionLoading,
  onToggle,
}: {
  plugin: PluginDetail;
  actionLoading: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
        <LayoutDashboard className="h-4 w-4" />
        {t('dashboardPanel.title')}
      </h4>
      <p className="text-xs text-slate-500 mb-4">
        {t('dashboardPanel.description')}
      </p>
      <div className="flex items-center justify-between">
        <span className={`text-sm ${plugin.dashboard_panel_enabled ? 'text-green-400' : 'text-slate-500'}`}>
          {plugin.dashboard_panel_enabled ? t('dashboardPanel.active') : t('dashboardPanel.inactive')}
        </span>
        <button
          onClick={onToggle}
          disabled={actionLoading}
          className={`rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 border ${
            plugin.dashboard_panel_enabled
              ? 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30'
              : 'border-green-500/30 bg-green-500/20 text-green-400 hover:bg-green-500/30'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {plugin.dashboard_panel_enabled ? t('buttons.disablePanel') : t('buttons.enablePanel')}
        </button>
      </div>
    </div>
  );
}
