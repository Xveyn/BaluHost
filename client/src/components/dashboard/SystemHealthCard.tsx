import { useTranslation } from 'react-i18next';
import type { SmartStatusResponse } from '../../api/smart';
import type { RaidStatusResponse } from '../../api/raid';
import { formatBytes, formatNumber } from '../../lib/formatters';

interface SystemHealthCardProps {
  smartData: SmartStatusResponse | null;
  smartLoading: boolean;
  smartError: string | null;
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
  storagePercent: number;
}

export function SystemHealthCard({
  smartData,
  smartLoading,
  smartError,
  raidData,
  raidLoading,
  storagePercent,
}: SystemHealthCardProps) {
  const { t } = useTranslation('dashboard');

  return (
    <div className="card border-slate-800/50 bg-slate-900/55">
      <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('health.title')}</p>
      <h3 className="mt-2 text-lg font-semibold text-white">{t('health.checksTitle')}</h3>
      <ul className="mt-5 space-y-3 text-sm text-slate-400">
        <li className="flex items-center justify-between">
          <span>{t('smart.subtitle')}</span>
          {smartLoading ? (
            <span className="text-slate-400">{t('health.checking')}</span>
          ) : smartError ? (
            <span className="text-rose-300">{t('health.error')}</span>
          ) : smartData && smartData.devices.every(d => d.status === 'PASSED') ? (
            <span className="text-emerald-300">{t('health.allDrivesOk')}</span>
          ) : (
            <span className="text-amber-300">{t('health.warningDetected')}</span>
          )}
        </li>
        <li className="flex items-center justify-between">
          <span>{t('system.raidStatus')}</span>
          {raidLoading ? (
            <span className="text-slate-400">{t('health.checking')}</span>
          ) : raidData && raidData.arrays.every(a => ['clean', 'optimal', 'checking'].includes(a.status)) ? (
            <span className="text-emerald-300">{t('health.arraysOptimal')}</span>
          ) : raidData && raidData.arrays.some(a => a.status.includes('degraded')) ? (
            <span className="text-amber-300">{t('health.degraded')}</span>
          ) : (
            <span className="text-slate-400">{t('health.noRaid')}</span>
          )}
        </li>
        <li className="flex items-center justify-between">
          <span>{t('health.physicalDrives')}</span>
          <span className="text-slate-200">
            {smartData ? t('health.detected', { count: smartData.devices.length }) : '—'}
          </span>
        </li>
        <li className="flex items-center justify-between">
          <span>{t('health.totalCapacity')}</span>
          <span className="text-slate-200">
            {smartData && smartData.devices.length > 0
              ? formatBytes(smartData.devices.reduce((sum, d) => sum + (d.capacity_bytes || 0), 0))
              : '—'
            }
          </span>
        </li>
        <li className="flex items-center justify-between">
          <span>{t('health.avgTemp')}</span>
          <span className="text-slate-200">
            {smartData && smartData.devices.length > 0
              ? `${Math.round(smartData.devices.reduce((sum, d) => sum + (d.temperature || 0), 0) / smartData.devices.length)}°C`
              : '—'
            }
          </span>
        </li>
        <li className="flex items-center justify-between">
          <span>{t('health.storageUsed')}</span>
          <span className="text-slate-200">{formatNumber(storagePercent, 1)}%</span>
        </li>
      </ul>
    </div>
  );
}
