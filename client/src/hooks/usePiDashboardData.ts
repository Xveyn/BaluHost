/**
 * BaluPi dashboard data (Pi build only).
 *
 * Query-backed (#299): replaces the page's hand-rolled 30s setInterval +
 * Promise.allSettled. Each of the four endpoints is its own `useQuery`, so a
 * single endpoint failing leaves the others intact (the allSettled semantics
 * the page relied on) and TanStack retains the last good value per slice.
 */
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import {
  getHandshakeStatus,
  getPiEnergyCurrent,
  getPiSystemStatus,
  getHandshakeSnapshot,
  type HandshakeStatus,
  type EnergyCurrent,
  type PiSystem,
  type SnapshotData,
} from '../api/pi';

export interface UsePiDashboardDataResult {
  handshake: HandshakeStatus | null;
  energy: EnergyCurrent | null;
  piSystem: PiSystem | null;
  snapshot: SnapshotData | null;
  refreshing: boolean;
  refetch: () => Promise<void>;
}

export function usePiDashboardData(pollInterval = 30000): UsePiDashboardDataResult {
  const handshake = useQuery({
    queryKey: queryKeys.pi.handshake(),
    queryFn: getHandshakeStatus,
    refetchInterval: pollInterval,
  });
  const energy = useQuery({
    queryKey: queryKeys.pi.energyCurrent(),
    queryFn: getPiEnergyCurrent,
    refetchInterval: pollInterval,
  });
  const system = useQuery({
    queryKey: queryKeys.pi.system(),
    queryFn: getPiSystemStatus,
    refetchInterval: pollInterval,
  });
  const snapshot = useQuery({
    queryKey: queryKeys.pi.snapshot(),
    queryFn: getHandshakeSnapshot,
    refetchInterval: pollInterval,
  });

  return {
    handshake: handshake.data ?? null,
    energy: energy.data ?? null,
    piSystem: system.data ?? null,
    snapshot: snapshot.data ?? null,
    refreshing:
      handshake.isFetching || energy.isFetching || system.isFetching || snapshot.isFetching,
    refetch: async () => {
      await Promise.all([
        handshake.refetch(),
        energy.refetch(),
        system.refetch(),
        snapshot.refetch(),
      ]);
    },
  };
}
