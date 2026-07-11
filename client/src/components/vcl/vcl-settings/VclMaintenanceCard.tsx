import { useTranslation } from 'react-i18next';
import { RefreshCw, Trash2 } from 'lucide-react';

export function VclMaintenanceCard({
  actionLoading,
  onDryRunCleanup,
  onTriggerCleanup,
  onRefresh,
}: {
  actionLoading: boolean;
  onDryRunCleanup: () => void;
  onTriggerCleanup: () => void;
  onRefresh: () => void;
}) {
  const { t } = useTranslation('admin');

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <RefreshCw className="w-5 h-5 text-sky-400" />
        {t('vcl.maintenance.title')}
      </h3>
      <div className="flex flex-wrap gap-3">
        <button
          onClick={onDryRunCleanup}
          disabled={actionLoading}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          {t('vcl.maintenance.dryRunCleanup')}
        </button>
        <button
          onClick={onTriggerCleanup}
          disabled={actionLoading}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <Trash2 className="w-4 h-4" />
          {t('vcl.maintenance.triggerCleanup')}
        </button>
        <button
          onClick={onRefresh}
          disabled={actionLoading}
          className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
          {t('vcl.maintenance.refreshStats')}
        </button>
      </div>
    </div>
  );
}
