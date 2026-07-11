/**
 * usePowerTabData -- data hook for SystemMonitor's PowerTab.
 *
 * Owns the two React Query calls (power devices/summary + cumulative energy)
 * and the derived read-values. Extracted verbatim from PowerTab.tsx (F2/#301).
 */
import { useQuery } from '@tanstack/react-query';
import { smartDevicesApi, type SmartDevice, type PowerSummary } from '../api/smart-devices';
import { getCumulativeEnergy, getCumulativeEnergyTotal, type CumulativeEnergyResponse } from '../api/energy';
import { queryKeys } from '../lib/queryKeys';
import { resolveCumulativeArgs } from '../lib/energyPolling';
import { getApiErrorMessage } from '../lib/errorHandling';
import { usePlugins } from '../contexts/PluginContext';

export interface UsePowerTabDataInput {
  selectedDeviceId: number | null;
  cumulativePeriod: 'today' | 'week' | 'month' | 'custom';
  customStart: string | null;
  customEnd: string | null;
}

export interface CumulativeKeyArgs {
  period: string;
  start: string | null;
  end: string | null;
}

export interface UsePowerTabDataResult {
  devices: SmartDevice[];
  powerSummary: PowerSummary | null;
  loading: boolean;
  error: string | null;
  cumulativeData: CumulativeEnergyResponse | null;
  cumulativeLoading: boolean;
  cumulativeReady: boolean;
  totalCurrentPower: number;
  powerPluginName: string | undefined;
  cumulativeKeyArgs: CumulativeKeyArgs;
}

export function usePowerTabData(input: UsePowerTabDataInput): UsePowerTabDataResult {
  const { selectedDeviceId, cumulativePeriod, customStart, customEnd } = input;
  const { plugins } = usePlugins();

  // Devices + power summary — query-backed (#299), 5s poll (per-device live watts
  // come from the device list). A 404 (no power plugin) is swallowed like before;
  // the last successful data is retained on any error.
  const powerQuery = useQuery({
    queryKey: queryKeys.powerTab.summary(),
    queryFn: async () => {
      const [listRes, summaryRes] = await Promise.all([
        smartDevicesApi.list(),
        smartDevicesApi.getPowerSummary(),
      ]);
      const powerDevices = listRes.data.devices.filter((d) => d.capabilities?.includes('power_monitor'));
      return { devices: powerDevices, powerSummary: summaryRes.data };
    },
    refetchInterval: 5000,
  });
  const devices = powerQuery.data?.devices ?? [];
  const powerSummary = powerQuery.data?.powerSummary ?? null;
  const loading = powerQuery.isLoading;
  const errorStatus =
    powerQuery.error && typeof powerQuery.error === 'object' && 'response' in powerQuery.error
      ? (powerQuery.error as { response?: { status?: number } }).response?.status
      : undefined;
  const error =
    powerQuery.isError && errorStatus !== 404
      ? getApiErrorMessage(powerQuery.error, 'Failed to load power data')
      : null;

  // Cumulative energy — query-backed 60s poll. `resolveCumulativeArgs` (tested)
  // maps the custom range; a custom period with nothing applied stays disabled.
  const rangeArgs = resolveCumulativeArgs(cumulativePeriod, customStart, customEnd);
  const cumulativeReady = !(cumulativePeriod === 'custom' && (!rangeArgs.start || !rangeArgs.end));
  const cumulativeQuery = useQuery({
    queryKey: queryKeys.powerTab.cumulative(
      selectedDeviceId,
      rangeArgs.period,
      rangeArgs.start ?? null,
      rangeArgs.end ?? null,
    ),
    queryFn: () =>
      selectedDeviceId === null
        ? getCumulativeEnergyTotal(rangeArgs.period, rangeArgs.start, rangeArgs.end)
        : getCumulativeEnergy(selectedDeviceId, rangeArgs.period, rangeArgs.start, rangeArgs.end),
    enabled: cumulativeReady,
    refetchInterval: 60000,
  });
  const cumulativeData = cumulativeQuery.data ?? null;
  // First-load spinner only — the old code re-showed it on every 60s poll.
  const cumulativeLoading = cumulativeQuery.isLoading;

  const totalCurrentPower = powerSummary?.total_watts ?? 0;
  const powerPluginName = devices.length > 0
    ? plugins.find(p => p.name === devices[0].plugin_name)?.display_name
    : undefined;

  const cumulativeKeyArgs: CumulativeKeyArgs = {
    period: rangeArgs.period,
    start: rangeArgs.start ?? null,
    end: rangeArgs.end ?? null,
  };

  return {
    devices,
    powerSummary,
    loading,
    error,
    cumulativeData,
    cumulativeLoading,
    cumulativeReady,
    totalCurrentPower,
    powerPluginName,
    cumulativeKeyArgs,
  };
}
