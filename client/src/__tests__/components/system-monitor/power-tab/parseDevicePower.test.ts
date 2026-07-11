import { describe, it, expect } from 'vitest';
import { parseDevicePower } from '../../../../components/system-monitor/power-tab/parseDevicePower';
import type { SmartDevice } from '../../../../api/smart-devices';

function dev(power_monitor: Record<string, unknown> | undefined): SmartDevice {
  return {
    id: 1, name: 'Plug', plugin_name: 'p', device_type_id: 't', address: 'a', mac_address: null,
    capabilities: ['power_monitor'], is_active: true, is_online: true, last_seen: null, last_error: null,
    state: power_monitor ? { power_monitor } : null, created_at: '', updated_at: '',
  };
}

describe('parseDevicePower', () => {
  it('prefers watts and current/energy in base units', () => {
    expect(parseDevicePower(dev({ watts: 12.5, voltage: 230, current: 0.05, energy_today_kwh: 1.2 })))
      .toEqual({ watts: 12.5, voltage: 230, currentA: 0.05, energyToday: 1.2 });
  });
  it('falls back to current_power, current_ma/1000, energy_today_wh/1000', () => {
    expect(parseDevicePower(dev({ current_power: 9, current_ma: 250, energy_today_wh: 800 })))
      .toEqual({ watts: 9, voltage: undefined, currentA: 0.25, energyToday: 0.8 });
  });
  it('returns all-undefined when power_monitor missing', () => {
    expect(parseDevicePower(dev(undefined))).toEqual({ watts: undefined, voltage: undefined, currentA: undefined, energyToday: undefined });
  });
});
