import { QueryClient } from '@tanstack/react-query';

/**
 * App-wide TanStack Query client.
 *
 * Defaults mirror the previous hand-rolled behavior:
 * - staleTime 0: freshness is driven by per-query refetchInterval, not staleTime.
 * - retry 1: the old code did not retry; keep a dead endpoint from hammering.
 * - refetchOnWindowFocus false: a polling LAN dashboard needs no focus refetch.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
