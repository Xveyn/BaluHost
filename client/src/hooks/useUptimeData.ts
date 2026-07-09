/**
 * Uptime monitoring data (current + history) for the SystemMonitor UptimeTab.
 *
 * Query-backed (#299): replaces the tab's hand-rolled 10s setInterval poller.
 * `current` and `history` share one poll interval; keys come from
 * queryKeys.monitoring.uptime*. The client-side 1s live-counter tick stays in
 * the component — it is an animation timer, not a data fetch.
 */
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getUptimeCurrent,
  getUptimeHistory,
  type TimeRange,
  type CurrentUptimeResponse,
  type UptimeSample,
  type SleepEvent,
} from '../api/monitoring';

export interface UseUptimeDataResult {
  current: CurrentUptimeResponse | null;
  history: UptimeSample[];
  sleepEvents: SleepEvent[];
  error: string | null;
}

export function useUptimeData(timeRange: TimeRange, pollInterval = 10000): UseUptimeDataResult {
  const current = useQuery({
    queryKey: queryKeys.monitoring.uptimeCurrent(),
    queryFn: getUptimeCurrent,
    refetchInterval: pollInterval,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.uptimeHistory(timeRange),
    queryFn: () => getUptimeHistory(timeRange),
    refetchInterval: pollInterval,
  });

  const err = current.error ?? history.error;
  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    sleepEvents: history.data?.sleep_events ?? [],
    error: err ? getApiErrorMessage(err, 'Failed to load uptime data') : null,
  };
}
