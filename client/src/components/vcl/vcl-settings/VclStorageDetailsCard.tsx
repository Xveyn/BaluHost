import { useTranslation } from 'react-i18next';
import { Database, Star } from 'lucide-react';
import { formatBytes } from '../../../api/vcl';
import { formatNumber } from '../../../lib/formatters';
import type { AdminVCLOverview } from '../../../types/vcl';

export function VclStorageDetailsCard({
  overview,
  compressionRatio,
}: {
  overview: AdminVCLOverview;
  compressionRatio: number;
}) {
  const { t } = useTranslation('admin');

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Database className="w-5 h-5 text-sky-400" />
        {t('vcl.storageDetails.title')}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.compressionRatio')}</p>
          <p className="text-white font-semibold mt-1">{formatNumber(compressionRatio, 2)}x</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.compressionSavings')}</p>
          <p className="text-white font-semibold mt-1">{formatBytes(overview.compression_savings_bytes)}</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.dedupSavings')}</p>
          <p className="text-white font-semibold mt-1">{formatBytes(overview.deduplication_savings_bytes)}</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.uniqueBlobs')}</p>
          <p className="text-white font-semibold mt-1">{overview.unique_blobs} / {overview.total_blobs}</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.priorityVersions')}</p>
          <p className="text-white font-semibold mt-1 flex items-center gap-1">
            <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
            {overview.priority_count}
          </p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.lastCleanup')}</p>
          <p className="text-white font-semibold mt-1">
            {overview.last_cleanup_at ? new Date(overview.last_cleanup_at).toLocaleDateString() : t('vcl.storageDetails.never')}
          </p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.lastPriorityMode')}</p>
          <p className="text-white font-semibold mt-1">
            {overview.last_priority_mode_at ? new Date(overview.last_priority_mode_at).toLocaleDateString() : t('vcl.storageDetails.never')}
          </p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageDetails.updated')}</p>
          <p className="text-white font-semibold mt-1">
            {overview.updated_at ? new Date(overview.updated_at).toLocaleTimeString() : t('common.na')}
          </p>
        </div>
      </div>
    </div>
  );
}
