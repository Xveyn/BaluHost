/**
 * Combined data for the PowerManagement page.
 *
 * Query-backed (#299): one `useQuery` whose queryFn fans out to the seven power
 * endpoints via Promise.all, replacing the page's hand-rolled 5s setInterval.
 * All-or-nothing (like the old Promise.all): any endpoint failing puts the
 * query in error; TanStack retains the last good combined snapshot. Mutations
 * on the page call `refetch()` to refresh.
 */
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getPowerStatus,
  listPresets,
  getPowerDemands,
  getServiceIntensities,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  getDynamicModeConfig,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type PowerHistoryEntry,
  type AutoScalingConfig,
  type ServiceIntensityInfo,
  type PowerPreset,
  type DynamicModeConfigResponse,
} from '../api/power-management';

export interface PowerManagementSnapshot {
  status: PowerStatusResponse;
  presets: PowerPreset[];
  demands: PowerDemandInfo[];
  intensities: ServiceIntensityInfo[];
  history: PowerHistoryEntry[];
  autoScaling: AutoScalingConfig;
  dynamicConfig: DynamicModeConfigResponse;
}

export interface UsePowerManagementDataResult {
  status: PowerStatusResponse | null;
  presets: PowerPreset[];
  demands: PowerDemandInfo[];
  intensities: ServiceIntensityInfo[];
  history: PowerHistoryEntry[];
  autoScaling: AutoScalingConfig | null;
  dynamicConfig: DynamicModeConfigResponse | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  /** Resolves to a success boolean (mirrors useRaidStatus) so the page can toast only on success. */
  refetch: () => Promise<boolean>;
}

async function fetchSnapshot(): Promise<PowerManagementSnapshot> {
  const [statusRes, presetsRes, demandsRes, intensitiesRes, historyRes, autoScalingRes, dynamicRes] =
    await Promise.all([
      getPowerStatus(),
      listPresets(),
      getPowerDemands(),
      getServiceIntensities(),
      getPowerMgmtHistory(50),
      getAutoScalingConfig(),
      getDynamicModeConfig(),
    ]);

  return {
    status: statusRes,
    presets: presetsRes.presets,
    demands: demandsRes,
    intensities: intensitiesRes.services,
    history: historyRes.entries,
    autoScaling: autoScalingRes.config,
    dynamicConfig: dynamicRes,
  };
}

export function usePowerManagementData(pollInterval = 5000): UsePowerManagementDataResult {
  const query = useQuery({
    queryKey: queryKeys.power.management(),
    queryFn: fetchSnapshot,
    refetchInterval: pollInterval,
  });

  const data = query.data;
  return {
    status: data?.status ?? null,
    presets: data?.presets ?? [],
    demands: data?.demands ?? [],
    intensities: data?.intensities ?? [],
    history: data?.history ?? [],
    autoScaling: data?.autoScaling ?? null,
    dynamicConfig: data?.dynamicConfig ?? null,
    loading: query.isLoading,
    error: query.error ? getApiErrorMessage(query.error, 'Failed to load power data') : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    refetch: async () => {
      const res = await query.refetch();
      return !res.isError;
    },
  };
}
