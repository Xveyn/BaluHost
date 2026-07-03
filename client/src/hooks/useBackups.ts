import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { listBackups, type Backup } from '../api/backup';

export interface UseBackupsResult {
  backups: Backup[];
  loading: boolean;
  /** Raw query error (null when none) — caller formats via getApiErrorMessage + i18n. */
  error: unknown;
}

/**
 * Backup list for BackupSettings. Query-backed — the two mount points
 * (BackupPage + SystemControlPage backup tab) share one cache entry.
 * No polling: create/delete mutations invalidate queryKeys.backups.list().
 */
export function useBackups(): UseBackupsResult {
  const query = useQuery({
    queryKey: queryKeys.backups.list(),
    queryFn: listBackups,
  });

  return {
    backups: query.data?.backups ?? [],
    loading: query.isLoading,
    error: query.isError ? query.error : null,
  };
}
