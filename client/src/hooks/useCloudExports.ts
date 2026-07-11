import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  listCloudExports,
  getCloudExportStatistics,
  revokeCloudExport,
  retryCloudExport,
  type CloudExportJob,
  type CloudExportStatistics,
} from '../api/cloud-export';

export interface UseCloudExportsResult {
  cloudExports: CloudExportJob[];
  cloudStats: CloudExportStatistics | null;
  loading: boolean;
  reload: () => Promise<void>;
  revoke: (jobId: number) => Promise<void>;
  retry: (jobId: number) => Promise<void>;
}

/**
 * Cloud-export list/stats + revoke/retry actions.
 *
 * Deliberately NOT TanStack Query (unlike the hooks/CLAUDE.md convention):
 * cloud exports are user-triggered, low-frequency data with no background
 * polling — one-shot load on mount + explicit reload after an action.
 * revoke/retry do NOT prompt; the page wraps revoke with a confirm dialog.
 */
export function useCloudExports(): UseCloudExportsResult {
  const { t } = useTranslation(['shares']);
  const [cloudExports, setCloudExports] = useState<CloudExportJob[]>([]);
  const [cloudStats, setCloudStats] = useState<CloudExportStatistics | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [cExports, cStats] = await Promise.all([
        listCloudExports().catch(() => []),
        getCloudExportStatistics().catch(() => null),
      ]);
      setCloudExports(cExports);
      setCloudStats(cStats);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const revoke = useCallback(async (jobId: number) => {
    try {
      await revokeCloudExport(jobId);
      await reload();
      toast.success(t('shares:cloudExport.revoked', 'Cloud share revoked'));
    } catch {
      toast.error(t('shares:cloudExport.revokeFailed', 'Failed to revoke cloud share'));
    }
  }, [reload, t]);

  const retry = useCallback(async (jobId: number) => {
    try {
      await retryCloudExport(jobId);
      await reload();
      toast.success(t('shares:cloudExport.retryStarted', 'Retry started'));
    } catch {
      toast.error(t('shares:cloudExport.retryFailed', 'Retry failed'));
    }
  }, [reload, t]);

  return { cloudExports, cloudStats, loading, reload, revoke, retry };
}
