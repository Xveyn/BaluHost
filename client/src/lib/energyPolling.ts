export type EnergyTimeWindow = '10min' | '1hour' | '24hours' | '7days';

/**
 * Poll cadence for the EnergyMonitor chart: 5s for the live 10-minute window,
 * 30s for the historical windows. Pure so it can be unit-tested without driving
 * TanStack's scheduler.
 */
export function energyChartRefreshInterval(window: EnergyTimeWindow): number {
  return window === '10min' ? 5000 : 30000;
}

export type CumulativePeriod = 'today' | 'week' | 'month' | 'custom';

interface CumulativeArgs {
  period: 'today' | 'week' | 'month';
  start?: string;
  end?: string;
}

/**
 * Resolve the cumulative-energy API args for the active PowerTab selection: a
 * custom range maps to `period: 'today'` plus explicit start/end bounds, a preset
 * passes through with no bounds. Pure — extracted from the old `resolveRangeArgs`
 * callback so the query key + fetch never drift and the mapping is unit-tested.
 */
export function resolveCumulativeArgs(
  period: CumulativePeriod,
  customStart: string | null,
  customEnd: string | null,
): CumulativeArgs {
  const isCustom = period === 'custom';
  return {
    period: isCustom ? 'today' : period,
    start: isCustom ? customStart ?? undefined : undefined,
    end: isCustom ? customEnd ?? undefined : undefined,
  };
}
