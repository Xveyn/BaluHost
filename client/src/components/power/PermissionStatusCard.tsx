import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import type { PowerStatusResponse } from '../../api/power-management';

interface PermissionStatusCardProps {
  status: PowerStatusResponse | null;
}

export function PermissionStatusCard({ status }: PermissionStatusCardProps) {
  const { t } = useTranslation(['system', 'common']);
  if (!status?.is_using_linux_backend || !status.permission_status) return null;
  return (
    <>
      {/* Permission Warning Banner */}
      {!status.permission_status.has_write_access && (
        <div data-testid="power-permission-warning" className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-amber-200">
                {t('system:power.permissions.warningTitle')}
              </h3>
              <p className="text-sm text-amber-300 mt-1">
                {t('system:power.permissions.warningMessage')}
              </p>
              <div className="mt-3 text-sm text-amber-300/80">
                <p className="font-medium mb-1">{t('system:power.permissions.suggestions')}</p>
                <ul className="list-disc list-inside space-y-1 font-mono text-xs">
                  <li>sudo systemctl start baluhost-backend</li>
                  <li>sudo usermod -aG cpufreq $USER</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Permission Status (Linux backend only) */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.permissions.title')}</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
          {/* Write Access Status */}
          <div className={`rounded-lg border p-2 sm:p-4 ${
            status.permission_status.has_write_access
              ? 'border-emerald-500/30 bg-emerald-500/10'
              : 'border-red-500/30 bg-red-500/10'
          }`}>
            <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.writeAccess')}</p>
            <p className={`text-sm sm:text-xl font-semibold ${
              status.permission_status.has_write_access ? 'text-emerald-300' : 'text-red-300'
            }`}>
              {status.permission_status.has_write_access ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
            </p>
          </div>

          {/* User Info */}
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
            <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.user')}</p>
            <p className="text-sm sm:text-xl font-semibold text-white truncate">{status.permission_status.user}</p>
          </div>

          {/* cpufreq Group Status */}
          <div className={`rounded-lg border p-2 sm:p-4 ${
            status.permission_status.in_cpufreq_group
              ? 'border-emerald-500/30 bg-emerald-500/10'
              : 'border-amber-500/30 bg-amber-500/10'
          }`}>
            <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.cpufreq')}</p>
            <p className={`text-sm sm:text-xl font-semibold ${
              status.permission_status.in_cpufreq_group ? 'text-emerald-300' : 'text-amber-300'
            }`}>
              {status.permission_status.in_cpufreq_group ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
            </p>
          </div>

          {/* Sudo Status */}
          <div className={`rounded-lg border p-2 sm:p-4 ${
            status.permission_status.sudo_available
              ? 'border-emerald-500/30 bg-emerald-500/10'
              : 'border-slate-700/50 bg-slate-800/30'
          }`}>
            <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.sudo')}</p>
            <p className={`text-sm sm:text-xl font-semibold ${
              status.permission_status.sudo_available ? 'text-emerald-300' : 'text-slate-400'
            }`}>
              {status.permission_status.sudo_available ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
