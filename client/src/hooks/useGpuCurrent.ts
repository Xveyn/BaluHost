import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getGpuCurrent, type GpuSample } from '../api/monitoring';

const POLL_MS = 3000;

/**
 * Current GPU sample via TanStack Query (#299). Replaces the two hand-rolled
 * `setInterval` pollers in `GpuTab` and `Dashboard` — both mount this hook so
 * the `gpu.current` key collapses them into one cache entry + one 3s poll.
 *
 * On a transient fetch error TanStack keeps the last successful `data`, so the
 * UI retains its previous reading (matching the old "keep last value" catch).
 * Pass `enabled: false` to suspend polling (Dashboard gates on GPU presence).
 */
export function useGpuCurrent(enabled = true): GpuSample | null {
  const { data } = useQuery({
    queryKey: queryKeys.gpu.current(),
    queryFn: getGpuCurrent,
    enabled,
    refetchInterval: POLL_MS,
  });
  return data ?? null;
}
