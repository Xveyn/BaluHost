import { useTranslation } from 'react-i18next';
import { Plug, Shield } from 'lucide-react';
import type { PluginInfo } from '../../../api/plugins';
import { resolvePluginString } from '../../../lib/pluginI18n';
import { getCategoryColor } from './pluginCategoryColor';

export function PluginListCard({
  plugin,
  isSelected,
  actionLoading,
  onSelect,
  onToggle,
}: {
  plugin: PluginInfo;
  isSelected: boolean;
  actionLoading: boolean;
  onSelect: (name: string) => void;
  onToggle: (plugin: PluginInfo) => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div
      onClick={() => onSelect(plugin.name)}
      className={`rounded-xl border p-4 cursor-pointer transition-all ${
        isSelected
          ? 'border-blue-500 bg-slate-900/80'
          : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${plugin.is_enabled ? 'bg-green-500/20' : 'bg-slate-800'}`}>
            <Plug className={`h-5 w-5 ${plugin.is_enabled ? 'text-green-400' : 'text-slate-500'}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-white">{resolvePluginString(plugin.translations, 'display_name', plugin.display_name)}</h3>
              <span className="text-xs text-slate-500">v{plugin.version}</span>
              {plugin.is_enabled && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                  {t('status.active')}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-400 mt-0.5">{resolvePluginString(plugin.translations, 'description', plugin.description)}</p>
            <div className="flex items-center gap-2 mt-2">
              <span className={`px-2 py-0.5 text-xs rounded-full border ${getCategoryColor(plugin.category)}`}>
                {plugin.category}
              </span>
              {plugin.has_ui && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">
                  {t('ui')}
                </span>
              )}
              {plugin.dangerous_permissions.length > 0 && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                  <Shield className="h-3 w-3" />
                  {t('permissions.requiresReview')}
                </span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(plugin);
          }}
          disabled={actionLoading}
          className={`rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
            plugin.is_enabled
              ? 'bg-slate-800 text-slate-300 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30'
              : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30'
          } border border-slate-700`}
        >
          {plugin.is_enabled ? t('buttons.disable') : t('buttons.enable')}
        </button>
      </div>
      {plugin.error && (
        <div className="mt-3 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
          Error: {plugin.error}
        </div>
      )}
    </div>
  );
}
