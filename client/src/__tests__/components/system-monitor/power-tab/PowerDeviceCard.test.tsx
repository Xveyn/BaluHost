import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fallback?: string) => fallback ?? k }) }));
vi.mock('../../../../lib/formatters', () => ({ formatNumber: (value: number, decimals: number) => value.toFixed(decimals) }));

import { PowerDeviceCard } from '../../../../components/system-monitor/power-tab/PowerDeviceCard';
import type { SmartDevice } from '../../../../api/smart-devices';

function makeDevice(overrides: Partial<SmartDevice>): SmartDevice {
  return {
    id: 1,
    name: 'Test Device',
    plugin_name: 'test-plugin',
    device_type_id: 'test-type',
    address: '127.0.0.1',
    mac_address: null,
    capabilities: [],
    is_active: true,
    is_online: true,
    last_seen: null,
    last_error: null,
    state: null,
    created_at: '',
    updated_at: '',
    ...overrides,
  };
}

describe('PowerDeviceCard', () => {
  it('renders device name, online badge, and power metrics', () => {
    const device = makeDevice({
      name: 'Living Room Plug',
      is_online: true,
      state: {
        power_monitor: { watts: 12.5, voltage: 230, current: 0.05, energy_today_kwh: 1.2 },
      },
    });

    render(<PowerDeviceCard device={device} />);

    expect(screen.getByText('Living Room Plug')).toBeTruthy();
    expect(screen.getByText('Online')).toBeTruthy();
    expect(screen.getByText('12.5')).toBeTruthy();
    expect(screen.getByText('230.0')).toBeTruthy();
    expect(screen.getByText('0.050')).toBeTruthy();
    expect(screen.getByText('1.20')).toBeTruthy();
  });

  it('renders offline badge and dash fallbacks when state is missing', () => {
    const device = makeDevice({
      name: 'Offline Plug',
      is_online: false,
      state: null,
    });

    render(<PowerDeviceCard device={device} />);

    expect(screen.getByText('Offline Plug')).toBeTruthy();
    expect(screen.getByText('Offline')).toBeTruthy();
    expect(screen.getAllByText('-')).toHaveLength(4);
  });
});
