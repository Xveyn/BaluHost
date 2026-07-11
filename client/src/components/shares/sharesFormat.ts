import { formatBytes } from '../../lib/formatters';
import type { CloudExportJob } from '../../api/cloud-export';

/** Localized date or the caller-provided "never" label for null. */
export function formatDate(dateString: string | null, neverLabel: string): string {
  if (!dateString) return neverLabel;
  return new Date(dateString).toLocaleDateString();
}

export function formatFileSize(bytes: number | null): string {
  if (!bytes) return '0 B';
  return formatBytes(bytes);
}

export function getProviderLabel(job: CloudExportJob): string {
  if (job.share_link?.includes('drive.google')) return 'Google Drive';
  if (job.share_link?.includes('1drv.ms') || job.share_link?.includes('sharepoint')) return 'OneDrive';
  return 'Cloud';
}
