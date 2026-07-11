import { useTranslation } from 'react-i18next';
import { HardDrive, Users, TrendingUp, Clock } from 'lucide-react';
import { formatBytes } from '../../../api/vcl';
import { formatNumber } from '../../../lib/formatters';
import type { AdminVCLOverview } from '../../../types/vcl';

export function VclStatsGrid({
  overview,
  totalSavings,
  savingsPercent,
}: {
  overview: AdminVCLOverview;
  totalSavings: number;
  savingsPercent: number;
}) {
  const { t } = useTranslation('admin');

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">{t('vcl.stats.totalVersions')}</p>
            <p className="text-2xl font-bold text-white mt-1">{overview.total_versions.toLocaleString()}</p>
          </div>
          <Clock className="w-10 h-10 text-sky-400 opacity-50" />
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">{t('vcl.stats.storageUsed')}</p>
            <p className="text-2xl font-bold text-white mt-1">{formatBytes(overview.total_compressed_bytes)}</p>
            <p className="text-xs text-slate-500 mt-1">{formatBytes(overview.total_size_bytes)} {t('vcl.stats.original')}</p>
          </div>
          <HardDrive className="w-10 h-10 text-violet-400 opacity-50" />
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">{t('vcl.stats.totalSavings')}</p>
            <p className="text-2xl font-bold text-white mt-1">{formatNumber(savingsPercent, 1)}%</p>
            <p className="text-xs text-slate-500 mt-1">{formatBytes(totalSavings)} {t('vcl.stats.saved')}</p>
          </div>
          <TrendingUp className="w-10 h-10 text-green-400 opacity-50" />
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">{t('vcl.stats.activeUsers')}</p>
            <p className="text-2xl font-bold text-white mt-1">{overview.total_users}</p>
            <p className="text-xs text-slate-500 mt-1">{overview.cached_versions_count} {t('vcl.stats.cached')}</p>
          </div>
          <Users className="w-10 h-10 text-amber-400 opacity-50" />
        </div>
      </div>
    </div>
  );
}
