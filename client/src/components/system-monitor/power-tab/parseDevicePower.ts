import type { SmartDevice } from '../../../api/smart-devices';

export interface DevicePower {
  watts?: number;
  voltage?: number;
  currentA?: number;
  energyToday?: number;
}

export function parseDevicePower(device: SmartDevice): DevicePower {
  const pm = device.state?.power_monitor as
    | { watts?: number; current_power?: number; voltage?: number; current?: number; current_ma?: number; energy_today_kwh?: number; energy_today_wh?: number }
    | undefined;
  const watts = pm?.watts ?? pm?.current_power;
  const voltage = pm?.voltage;
  const currentA = pm?.current ?? (pm?.current_ma != null ? pm.current_ma / 1000 : undefined);
  const energyToday = pm?.energy_today_kwh ?? (pm?.energy_today_wh != null ? pm.energy_today_wh / 1000 : undefined);
  return { watts, voltage, currentA, energyToday };
}
