import { useTranslation } from 'react-i18next';
import { Shield, Check, X } from 'lucide-react';
import type { PluginDetail } from '../../../api/plugins';

export function PluginPermissionsCard({ plugin }: { plugin: PluginDetail }) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
        <Shield className="h-4 w-4" />
        {t('permissions.title')}
      </h4>
      {plugin.required_permissions.length === 0 ? (
        <p className="text-sm text-slate-500">{t('permissions.noPermissions')}</p>
      ) : (
        <ul className="space-y-2">
          {plugin.required_permissions.map((perm) => {
            const isDangerous = plugin.dangerous_permissions.includes(perm);
            const isGranted = plugin.granted_permissions.includes(perm);
            return (
              <li
                key={perm}
                className={`flex items-center justify-between text-sm p-2 rounded-lg ${
                  isDangerous
                    ? 'bg-amber-500/10 border border-amber-500/20'
                    : 'bg-slate-800/50'
                }`}
              >
                <span className={isDangerous ? 'text-amber-400' : 'text-slate-300'}>
                  {perm}
                </span>
                {isGranted ? (
                  <Check className="h-4 w-4 text-green-400" />
                ) : (
                  <X className="h-4 w-4 text-slate-500" />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
