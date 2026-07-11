import { useTranslation } from 'react-i18next';
import type { PluginDetail, PermissionInfo } from '../../../api/plugins';

export function PermissionGrantModal({
  plugin,
  allPermissions,
  selectedPermissions,
  onTogglePermission,
  onCancel,
  onConfirm,
}: {
  plugin: PluginDetail;
  allPermissions: PermissionInfo[];
  selectedPermissions: string[];
  onTogglePermission: (perm: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h3 className="text-lg font-medium text-white mb-2">
          {t('modal.enableTitle', { name: plugin.display_name })}
        </h3>
        <p className="text-sm text-slate-400 mb-4">
          {t('modal.enableDesc')}
        </p>
        <div className="space-y-2 mb-6 max-h-64 overflow-y-auto">
          {plugin.required_permissions.map((perm) => {
            const permInfo = allPermissions.find((p) => p.value === perm);
            const isChecked = selectedPermissions.includes(perm);
            return (
              <label
                key={perm}
                className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition ${
                  permInfo?.dangerous
                    ? 'bg-amber-500/10 border border-amber-500/20'
                    : 'bg-slate-800/50 border border-slate-700'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onTogglePermission(perm)}
                  className="mt-1 rounded border-slate-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-900"
                />
                <div>
                  <div className={`text-sm font-medium ${permInfo?.dangerous ? 'text-amber-400' : 'text-white'}`}>
                    {perm}
                    {permInfo?.dangerous && (
                      <span className="ml-2 text-xs text-amber-500">({t('permissions.dangerous')})</span>
                    )}
                  </div>
                  {permInfo && (
                    <p className="text-xs text-slate-500 mt-0.5">{permInfo.description}</p>
                  )}
                </div>
              </label>
            );
          })}
        </div>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 transition-all touch-manipulation active:scale-95"
          >
            {t('buttons.cancel')}
          </button>
          <button
            onClick={onConfirm}
            disabled={!plugin.required_permissions.every((p) => selectedPermissions.includes(p))}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all touch-manipulation active:scale-95"
          >
            {t('buttons.enablePlugin')}
          </button>
        </div>
      </div>
    </div>
  );
}
