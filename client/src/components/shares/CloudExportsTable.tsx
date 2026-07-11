import { useTranslation } from 'react-i18next';
import { Cloud, Copy, Trash2, RefreshCw, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { CloudStatusBadge } from './CloudStatusBadge';
import { FileNameCell } from './FileNameCell';
import { formatDate, getProviderLabel } from './sharesFormat';
import type { CloudExportJob } from '../../api/cloud-export';
import type { SortProps } from './types';

interface CloudExportsTableProps extends SortProps {
  jobs: CloudExportJob[];
  onCopyLink: (link: string) => void;
  onRevoke: (jobId: number) => void;
  onRetry: (jobId: number) => void;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function CloudExportsTable({ jobs, sortKey, sortDirection, onSort, onCopyLink, onRevoke, onRetry }: CloudExportsTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (jobs.length === 0) {
    return (
      <EmptyState
        icon={Cloud}
        title={t('shares:cloudExport.noExports', 'No cloud shares')}
        description={t('shares:cloudExport.noExportsDesc', 'Share files to cloud storage from the file manager.')}
      />
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label={t('shares:cloudExport.provider', 'Provider')} sortKey="provider" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('shares:cloudExport.link', 'Link')}</th>
              <SortableHeader label={t('search.status', 'Status')} sortKey="status" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('shares:cloudExport.created', 'Created')} sortKey="created_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {jobs.map((job) => (
              <tr key={job.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4"><span className="text-slate-300 font-medium">{getProviderLabel(job)}</span></td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={job.is_directory} name={job.file_name} size={job.file_size_bytes} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  {job.share_link ? (
                    <button onClick={() => onCopyLink(job.share_link!)} className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-sm" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                      <Copy className="w-3.5 h-3.5" />
                      <span className="truncate max-w-[160px]">{t('shares:cloudExport.copyLink', 'Copy link')}</span>
                    </button>
                  ) : (
                    <span className="text-slate-500 text-sm">--</span>
                  )}
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4"><CloudStatusBadge job={job} /></td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(job.created_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(job.expires_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    {job.share_link && (
                      <button onClick={() => onCopyLink(job.share_link!)} className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition hover:border-blue-500/50 hover:bg-blue-500/20" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                        <Copy className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                    {job.status === 'ready' && (
                      <button onClick={() => onRevoke(job.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20" title={t('shares:cloudExport.revoke', 'Revoke')}>
                        <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                    {job.status === 'failed' && (
                      <button onClick={() => onRetry(job.id)} className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20" title={t('shares:cloudExport.retry', 'Retry')}>
                        <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5" />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {jobs.map((job) => (
          <div key={job.id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <div className="flex items-start justify-between gap-2 mb-3">
              <FileNameCell variant="card" className="min-w-0 flex-1" isDirectory={job.is_directory} name={job.file_name} size={job.file_size_bytes} folderLabel={folderLabel} />
              <div className="flex gap-1 flex-shrink-0">
                {job.share_link && (
                  <button onClick={() => onCopyLink(job.share_link!)} className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.copyLink', 'Copy link')}>
                    <Copy className="w-4 h-4" />
                  </button>
                )}
                {job.status === 'ready' && (
                  <button onClick={() => onRevoke(job.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.revoke', 'Revoke')}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
                {job.status === 'failed' && (
                  <button onClick={() => onRetry(job.id)} className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition touch-manipulation active:scale-95" title={t('shares:cloudExport.retry', 'Retry')}>
                    <RefreshCw className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Cloud className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{getProviderLabel(job)}</span>
            </div>
            <div className="flex items-center gap-2 mb-2"><CloudStatusBadge job={job} /></div>
            {job.share_link && (
              <button onClick={() => onCopyLink(job.share_link!)} className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-xs mb-2">
                <Copy className="w-3 h-3" />
                {t('shares:cloudExport.copyLink', 'Copy link')}
              </button>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('shares:cloudExport.created', 'Created')}: {formatDate(job.created_at, never)}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.expires')}: {formatDate(job.expires_at, never)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
