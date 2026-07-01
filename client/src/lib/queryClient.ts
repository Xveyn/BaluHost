import { QueryClient } from '@tanstack/react-query';

/**
 * App-wide TanStack Query client.
 *
 * Defaults mirror the previous hand-rolled behavior:
 * - staleTime 0: freshness is driven by per-query refetchInterval, not staleTime.
 * - retry 1: one retry on failure (down from TanStack's default of 3) so a
 *   dead endpoint isn't hammered with repeated attempts.
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
