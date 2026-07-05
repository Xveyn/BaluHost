export type EnergyTimeWindow = '10min' | '1hour' | '24hours' | '7days';

/**
 * Poll cadence for the EnergyMonitor chart: 5s for the live 10-minute window,
 * 30s for the historical windows. Pure so it can be unit-tested without driving
 * TanStack's scheduler.
 */
export function energyChartRefreshInterval(window: EnergyTimeWindow): number {
  return window === '10min' ? 5000 : 30000;
}
