import { useTranslation } from 'react-i18next';
import { Users } from 'lucide-react';
import { formatBytes } from '../../../api/vcl';
import { formatNumber } from '../../../lib/formatters';
import { usageBarColor } from './usageBarColor';
import type { UserVCLStats } from '../../../types/vcl';

export function VclUserQuotasTable({
  users,
  onEditUser,
}: {
  users: UserVCLStats[];
  onEditUser: (user: UserVCLStats) => void;
}) {
  const { t } = useTranslation('admin');

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Users className="w-5 h-5 text-sky-400" />
        {t('vcl.userQuotas.title')}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-slate-800">
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.user')}</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.maxSize')}</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.used')}</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.usage')}</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.versions')}</th>
              <th className="pb-3 text-slate-400 font-medium">Mode</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.status')}</th>
              <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users && users.length > 0 ? users.map((user) => {
              const usagePercent = user.usage_percent;
              const isWarning = usagePercent >= 80;
              const isCritical = usagePercent >= 95;

              return (
                <tr key={user.user_id} className="border-b border-slate-800/50">
                  <td className="py-3 text-white font-medium">{user.username}</td>
                  <td className="py-3 text-slate-300">{formatBytes(user.max_size_bytes)}</td>
                  <td className="py-3 text-slate-300">{formatBytes(user.current_usage_bytes)}</td>
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden max-w-[100px]">
                        <div
                          className={`h-full transition-all ${usageBarColor(usagePercent, 80, 95)}`}
                          style={{ width: `${Math.min(usagePercent, 100)}%` }}
                        />
                      </div>
                      <span className={`${isCritical ? 'text-red-400' : isWarning ? 'text-amber-400' : 'text-slate-300'}`}>
                        {formatNumber(usagePercent, 1)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 text-slate-300">{user.total_versions}</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      user.vcl_mode === 'manual'
                        ? 'bg-violet-500/20 text-violet-300'
                        : 'bg-sky-500/20 text-sky-300'
                    }`}>
                      {user.vcl_mode === 'manual' ? 'Manual' : 'Auto'}
                    </span>
                  </td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                        user.is_enabled
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {user.is_enabled ? t('common.enabled') : t('common.disabled')}
                    </span>
                  </td>
                  <td className="py-3">
                    <button
                      onClick={() => onEditUser(user)}
                      className="text-sky-400 hover:text-sky-300 transition-colors"
                    >
                      {t('common.edit')}
                    </button>
                  </td>
                </tr>
              );
            }) : (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500">
                  {t('vcl.userQuotas.noUsers')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
