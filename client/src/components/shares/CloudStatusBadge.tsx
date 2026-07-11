import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import type { CloudExportJob } from '../../api/cloud-export';

export function CloudStatusBadge({ job }: { job: CloudExportJob }) {
  const { t } = useTranslation('shares');
  switch (job.status) {
    case 'ready':
      return <span className="px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusReady', 'Ready')}</span>;
    case 'uploading':
    case 'creating_link':
      return (
        <span className="px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-semibold inline-flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" />
          {job.status === 'uploading'
            ? (job.file_size_bytes
              ? `${Math.round((job.progress_bytes / job.file_size_bytes) * 100)}%`
              : t('shares:cloudExport.statusUploading', 'Uploading'))
            : t('shares:cloudExport.statusCreatingLink', 'Creating link')}
        </span>
      );
    case 'pending':
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusPending', 'Pending')}</span>;
    case 'failed':
      return <span className="px-2.5 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusFailed', 'Failed')}</span>;
    case 'revoked':
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-500 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusRevoked', 'Revoked')}</span>;
    default:
      return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{job.status}</span>;
  }
}
