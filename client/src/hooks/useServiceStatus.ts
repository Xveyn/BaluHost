import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getDebugSnapshot,
  restartService,
  stopService,
  startService,
  type AdminDebugSnapshot,
} from '../api/service-status';

interface UseDebugSnapshotOptions {
  enabled?: boolean;
  pollInterval?: number;
}

interface UseDebugSnapshotReturn {
  snapshot: AdminDebugSnapshot | null;
  isLoading: boolean;
  isFetching: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refetch: () => Promise<void>;
}

/**
 * Admin debug snapshot (services + dependencies + metrics) via TanStack Query
 * (#299). `refetchInterval` replaces the two hand-rolled 10s setInterval pollers
 * in ServicesTab + ServicesStatusTab — the shared `services.debugSnapshot()` key
 * collapses them into one cache entry + one poll. Pass `enabled: false` to
 * suspend fetching (ServicesTab gates on admin).
 */
export function useDebugSnapshot(options: UseDebugSnapshotOptions = {}): UseDebugSnapshotReturn {
  const { enabled = true, pollInterval = 10000 } = options;

  const query = useQuery({
    queryKey: queryKeys.services.debugSnapshot(),
    queryFn: getDebugSnapshot,
    enabled,
    refetchInterval: pollInterval > 0 ? pollInterval : false,
  });

  return {
    snapshot: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load service status') : null,
    lastUpdated: query.data && query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}

interface UseServiceControlsReturn {
  restart: (serviceName: string) => Promise<void>;
  stop: (serviceName: string) => Promise<void>;
  start: (serviceName: string) => Promise<void>;
}

/**
 * Service control actions (restart/stop/start) via `useMutation` (#299). Each
 * toasts success/failure exactly like the old imperative handlers and, on
 * settle, invalidates the whole `services` domain so both the debug snapshot and
 * the dashboard summary refresh. `mutateAsync` rejections are already surfaced
 * via `onError`, so the returned wrappers swallow them to avoid unhandled
 * rejections at the call site.
 */
export function useServiceControls(): UseServiceControlsReturn {
  const { t } = useTranslation(['system']);
  const queryClient = useQueryClient();
  const onSettled = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.services.all() });
  };

  const restartMutation = useMutation({
    mutationFn: (serviceName: string) => restartService(serviceName),
    onSuccess: (result, serviceName) => {
      if (result.success) toast.success(t('system:services.toast.restartSuccess', { name: serviceName }));
      else toast.error(result.message || t('system:services.toast.restartFailed', { name: serviceName }));
    },
    onError: (err, serviceName) =>
      toast.error(getApiErrorMessage(err, t('system:services.toast.restartFailed', { name: serviceName }))),
    onSettled,
  });

  const stopMutation = useMutation({
    mutationFn: (serviceName: string) => stopService(serviceName),
    onSuccess: (result, serviceName) => {
      if (result.success) toast.success(t('system:services.toast.stopSuccess', { name: serviceName }));
      else toast.error(result.message || t('system:services.toast.stopFailed', { name: serviceName }));
    },
    onError: (err, serviceName) =>
      toast.error(getApiErrorMessage(err, t('system:services.toast.stopFailed', { name: serviceName }))),
    onSettled,
  });

  const startMutation = useMutation({
    mutationFn: (serviceName: string) => startService(serviceName),
    onSuccess: (result, serviceName) => {
      if (result.success) toast.success(t('system:services.toast.startSuccess', { name: serviceName }));
      else toast.error(result.message || t('system:services.toast.startFailed', { name: serviceName }));
    },
    onError: (err, serviceName) =>
      toast.error(getApiErrorMessage(err, t('system:services.toast.startFailed', { name: serviceName }))),
    onSettled,
  });

  return {
    restart: (serviceName) => restartMutation.mutateAsync(serviceName).then(() => {}).catch(() => {}),
    stop: (serviceName) => stopMutation.mutateAsync(serviceName).then(() => {}).catch(() => {}),
    start: (serviceName) => startMutation.mutateAsync(serviceName).then(() => {}).catch(() => {}),
  };
}
