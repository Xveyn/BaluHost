import { useTranslation } from 'react-i18next';
import { FolderOpen } from 'lucide-react';
import { formatBytes } from '../../../api/vcl';
import { formatNumber } from '../../../lib/formatters';
import type { VCLStorageInfo } from '../../../types/vcl';
import { usageBarColor } from './usageBarColor';

export function VclStorageInfoCard({ storageInfo }: { storageInfo: VCLStorageInfo }) {
  const { t } = useTranslation('admin');

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <FolderOpen className="w-5 h-5 text-sky-400" />
        {t('vcl.storageInfo.title', 'Storage Location')}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-slate-400">{t('vcl.storageInfo.path', 'Storage Path')}</p>
          <p className="text-white font-semibold mt-1 truncate" title={storageInfo.storage_path}>
            {storageInfo.storage_path}
          </p>
          {storageInfo.is_custom_path && (
            <span className="mt-1 inline-block px-2 py-0.5 rounded-full text-[10px] font-medium bg-violet-500/20 text-violet-300">
              Custom Path
            </span>
          )}
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageInfo.blobCount', 'Blob Count')}</p>
          <p className="text-white font-semibold mt-1">{storageInfo.blob_count.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageInfo.compressedSize', 'Compressed Size')}</p>
          <p className="text-white font-semibold mt-1">{formatBytes(storageInfo.total_compressed_bytes)}</p>
        </div>
        <div>
          <p className="text-slate-400">{t('vcl.storageInfo.diskUsage', 'Disk Usage')}</p>
          <p className="text-white font-semibold mt-1">
            {formatNumber(storageInfo.disk_used_percent, 1)}%
          </p>
          <div className="h-1.5 w-full mt-1.5 overflow-hidden rounded-full bg-slate-800 max-w-[120px]">
            <div
              className={`h-full rounded-full transition-all ${usageBarColor(storageInfo.disk_used_percent, 70, 90)}`}
              style={{ width: `${Math.min(storageInfo.disk_used_percent, 100)}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {formatBytes(storageInfo.disk_available_bytes)} {t('vcl.storageInfo.free', 'free')} / {formatBytes(storageInfo.disk_total_bytes)}
          </p>
        </div>
      </div>
    </div>
  );
}
