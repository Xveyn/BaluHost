import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getStatusBarState } from '../api/statusBar';
import type { StatusBarStateResponse } from '../api/statusBar';

const POLL_MS = 10_000;

export interface UseStatusBarState {
  state: StatusBarStateResponse | null;
  stale: boolean;
}

/**
 * Status-bar strip state. Query-backed (#299): `refetchInterval` replaces the old
 * hand-rolled setInterval, and polling pauses automatically while the tab is hidden
 * (TanStack's `refetchIntervalInBackground` defaults to false — same intent as the
 * old `document.hidden` guard).
 *
 * Failure handling: TanStack retains the last successful `data` across failed polls,
 * so the strip keeps its last-known state and we surface `stale` once polls error.
 * This deliberately replaces the old "hide after 3 consecutive failures" behaviour —
 * the strip now stays visible-but-stale during an outage rather than disappearing.
 * `retry: false` keeps one attempt per poll (matching the old single-shot poller).
 */
export function useStatusBarState(): UseStatusBarState {
  const query = useQuery({
    queryKey: queryKeys.statusBar.state(),
    queryFn: getStatusBarState,
    refetchInterval: POLL_MS,
    retry: false,
  });

  return {
    state: query.data ?? null,
    stale: query.isError,
  };
}
