/**
 * VCL→SSD migration panel data.
 *
 * Query-backed (#299): storage info + job history as plain queries, plus a
 * tracked "active job" progress query that polls (3s) only while the job is
 * running/pending and refreshes the job history when it turns terminal —
 * replacing the panel's imperative startPolling/stopPolling + setInterval.
 */
import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getStorageInfo } from '../api/vcl';
import type { VCLStorageInfo } from '../types/vcl';
import { getMigrationJobs, getMigrationJob, type MigrationJobResponse } from '../api/migration';

const JOB_POLL_MS = 3000;

function isActiveStatus(status: string | undefined): boolean {
  return status === 'running' || status === 'pending';
}

export interface UseMigrationDataResult {
  storageInfo: VCLStorageInfo | null;
  jobs: MigrationJobResponse[];
  activeJob: MigrationJobResponse | null;
  loading: boolean;
  /** Start tracking a freshly-started job: shows it at once and polls until terminal. */
  trackJob: (job: MigrationJobResponse) => void;
  refetch: () => Promise<void>;
}

export function useMigrationData(): UseMigrationDataResult {
  const queryClient = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  const storage = useQuery({ queryKey: queryKeys.migration.storage(), queryFn: getStorageInfo });
  const jobsQuery = useQuery({ queryKey: queryKeys.migration.jobs(), queryFn: () => getMigrationJobs() });

  const activeJobQuery = useQuery({
    queryKey: queryKeys.migration.job(activeJobId),
    queryFn: () => getMigrationJob(activeJobId as number),
    enabled: activeJobId != null,
    refetchInterval: (query) => (isActiveStatus(query.state.data?.status) ? JOB_POLL_MS : false),
  });
  const activeJob = activeJobQuery.data ?? null;

  // Adopt a still-running job from the history when nothing is tracked yet.
  useEffect(() => {
    if (activeJobId != null) return;
    const running = jobsQuery.data?.find((j) => isActiveStatus(j.status));
    if (running) setActiveJobId(running.id);
  }, [jobsQuery.data, activeJobId]);

  // When the tracked job turns terminal, refresh the job history.
  const activeStatus = activeJob?.status;
  useEffect(() => {
    if (activeJobId != null && activeStatus && !isActiveStatus(activeStatus)) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.migration.jobs() });
    }
  }, [activeStatus, activeJobId, queryClient]);

  const trackJob = useCallback(
    (job: MigrationJobResponse) => {
      // Seed the cache so the just-started job renders before the first poll.
      queryClient.setQueryData(queryKeys.migration.job(job.id), job);
      setActiveJobId(job.id);
    },
    [queryClient],
  );

  return {
    storageInfo: storage.data ?? null,
    jobs: jobsQuery.data ?? [],
    activeJob,
    loading: storage.isLoading || jobsQuery.isLoading,
    trackJob,
    refetch: async () => {
      await Promise.all([storage.refetch(), jobsQuery.refetch()]);
    },
  };
}
