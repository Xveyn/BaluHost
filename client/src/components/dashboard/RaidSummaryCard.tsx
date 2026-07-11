import { useTranslation } from 'react-i18next';
import type { RaidStatusResponse } from '../../api/raid';
import { formatBytes, formatNumber } from '../../lib/formatters';

interface RaidSummaryCardProps {
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
}

export function RaidSummaryCard({ raidData, raidLoading }: RaidSummaryCardProps) {
  const { t } = useTranslation('dashboard');

  return (
    <div className="card border-slate-800/50 bg-slate-900/55">
      <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('raid.configTitle')}</p>
      <h3 className="mt-2 text-lg font-semibold text-white">{t('raid.title')}</h3>
      {raidLoading ? (
        <div className="mt-5 text-sm text-slate-500">{t('raid.loading')}</div>
      ) : raidData && raidData.arrays.length > 0 ? (
        <div className="mt-5 space-y-3">
          {raidData.arrays.map((array) => (
            <div key={array.name} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-100">{array.name}</p>
                  <p className="text-xs text-slate-500">RAID {array.level} • {formatBytes(array.size_bytes)}</p>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-xs ${
                  array.status === 'clean' || array.status === 'optimal'
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : array.status === 'checking'
                    ? 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300'
                    : array.status === 'rebuilding'
                    ? 'border-sky-500/30 bg-sky-500/10 text-sky-300'
                    : array.status.includes('degraded')
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                }`}>
                  {array.status}
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {t('raid.devices', { count: array.devices.length })} • {t('raid.active', { count: array.devices.filter(d => d.state.includes('active')).length })}
              </div>
              {array.resync_progress !== null && array.resync_progress !== undefined && (
                <div className="mt-2">
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                    <span>{t('raid.resyncProgress')}</span>
                    <span>{formatNumber(array.resync_progress, 1)}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
                      style={{ width: `${array.resync_progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-5 text-sm text-slate-500">{t('raid.noArrays')}</div>
      )}
    </div>
  );
}
