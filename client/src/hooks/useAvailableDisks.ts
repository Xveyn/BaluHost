import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getAvailableDisks, type AvailableDisk } from '../api/raid';

export interface UseAvailableDisksResult {
  disks: AvailableDisk[];
  loading: boolean;
  /** Raw query error (null when none) — caller formats via getApiErrorMessage. */
  error: unknown;
}

/**
 * Available (unassigned) disks for the RAID management page. Query-backed, no
 * polling — format/create/delete mutations invalidate queryKeys.raid.availableDisks()
 * (or the whole raid domain via queryKeys.raid.all()).
 */
export function useAvailableDisks(): UseAvailableDisksResult {
  const query = useQuery({
    queryKey: queryKeys.raid.availableDisks(),
    queryFn: getAvailableDisks,
  });

  return {
    disks: query.data?.disks ?? [],
    loading: query.isLoading,
    error: query.isError ? query.error : null,
  };
}
