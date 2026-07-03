import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import {
  listFileShares,
  listFilesSharedWithMe,
  getShareStatistics,
  type FileShare,
  type SharedWithMe,
  type ShareStatistics,
} from '../api/shares';

export interface UseFileSharesResult {
  fileShares: FileShare[];
  sharedWithMe: SharedWithMe[];
  statistics: ShareStatistics | null;
  loading: boolean;
  /** Raw error of the first failing query (null when all fine). */
  error: unknown;
}

/**
 * The three shares-domain reads for SharesPage (user-scoped!). Mutations
 * anywhere in the app invalidate queryKeys.shares.all() — see the share
 * modals. Cross-user leaking is prevented by AuthContext.clearQueryCache().
 */
export function useFileShares(): UseFileSharesResult {
  const userShares = useQuery({
    queryKey: queryKeys.shares.userShares(),
    queryFn: listFileShares,
  });
  const sharedWithMe = useQuery({
    queryKey: queryKeys.shares.sharedWithMe(),
    queryFn: listFilesSharedWithMe,
  });
  const statistics = useQuery({
    queryKey: queryKeys.shares.statistics(),
    queryFn: getShareStatistics,
  });

  const queries = [userShares, sharedWithMe, statistics];
  return {
    fileShares: userShares.data ?? [],
    sharedWithMe: sharedWithMe.data ?? [],
    statistics: statistics.data ?? null,
    loading: queries.some((q) => q.isLoading),
    error: queries.find((q) => q.isError)?.error ?? null,
  };
}
