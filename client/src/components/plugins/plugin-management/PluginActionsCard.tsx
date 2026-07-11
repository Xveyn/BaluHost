import { useTranslation } from 'react-i18next';
import { Settings, Trash2 } from 'lucide-react';
import type { PluginDetail } from '../../../api/plugins';
import { LocalOnlyAction } from '../../LocalOnlyAction';

export function PluginActionsCard({
  plugin,
  actionLoading,
  onConfigure,
  onUninstall,
}: {
  plugin: PluginDetail;
  actionLoading: boolean;
  onConfigure: () => void;
  onUninstall: (name: string) => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 space-y-3">
      <button
        onClick={onConfigure}
        disabled={!plugin.is_enabled}
        className="w-full px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all touch-manipulation active:scale-95"
      >
        <Settings className="h-4 w-4" />
        {t('buttons.configure')}
      </button>
      <LocalOnlyAction>
        <button
          onClick={() => onUninstall(plugin.name)}
          disabled={actionLoading || plugin.is_enabled}
          className="w-full px-4 py-2 text-sm font-medium rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all touch-manipulation active:scale-95"
        >
          <Trash2 className="h-4 w-4" />
          {t('buttons.uninstall')}
        </button>
      </LocalOnlyAction>
      {plugin.is_enabled && (
        <p className="text-xs text-slate-500 text-center">
          {t('confirm.disableFirst')}
        </p>
      )}
    </div>
  );
}
