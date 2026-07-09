/**
 * Cloud-import connections + jobs for the CloudImportPage.
 *
 * Query-backed (#299): replaces the page's hand-rolled conditional 3s
 * setInterval. The jobs query auto-polls (3s) only while a job is running or
 * pending — a function `refetchInterval` that returns false once every job is
 * terminal, so the poll stops on its own.
 */
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getConnections, getJobs, type CloudConnection, type CloudImportJob } from '../api/cloud-import';

const JOB_POLL_MS = 3000;

function hasActiveJob(jobs: CloudImportJob[] | undefined): boolean {
  return !!jobs?.some((j) => j.status === 'running' || j.status === 'pending');
}

export interface UseCloudImportDataResult {
  connections: CloudConnection[];
  jobs: CloudImportJob[];
  loading: boolean;
  refetch: () => Promise<void>;
}

export function useCloudImportData(): UseCloudImportDataResult {
  const connections = useQuery({
    queryKey: queryKeys.cloudImport.connections(),
    queryFn: getConnections,
  });
  const jobs = useQuery({
    queryKey: queryKeys.cloudImport.jobs(),
    queryFn: () => getJobs(),
    refetchInterval: (query) => (hasActiveJob(query.state.data) ? JOB_POLL_MS : false),
  });

  return {
    connections: connections.data ?? [],
    jobs: jobs.data ?? [],
    loading: connections.isLoading || jobs.isLoading,
    refetch: async () => {
      await Promise.all([connections.refetch(), jobs.refetch()]);
    },
  };
}
