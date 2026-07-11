import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { ChartDeviceTabs } from '../../../../components/system-monitor/power-tab/ChartDeviceTabs';
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

describe('ChartDeviceTabs', () => {
  const activeDevice = makeDevice({ id: 1, name: 'Living Room Plug', is_active: true, capabilities: ['power_monitor'] });
  const inactiveDevice = makeDevice({ id: 2, name: 'Inactive Plug', is_active: false, capabilities: ['power_monitor'] });

  it('renders Total and only active power_monitor devices', () => {
    render(
      <ChartDeviceTabs devices={[activeDevice, inactiveDevice]} selectedDeviceId={null} onSelect={vi.fn()} />
    );

    expect(screen.getByText('monitor.power.total')).toBeTruthy();
    expect(screen.getByText('Living Room Plug')).toBeTruthy();
    expect(screen.queryByText('Inactive Plug')).toBeNull();
  });

  it('calls onSelect with device id when a device tab is clicked', () => {
    const onSelect = vi.fn();
    render(
      <ChartDeviceTabs devices={[activeDevice, inactiveDevice]} selectedDeviceId={null} onSelect={onSelect} />
    );

    fireEvent.click(screen.getByText('Living Room Plug'));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('calls onSelect with null when Total is clicked', () => {
    const onSelect = vi.fn();
    render(
      <ChartDeviceTabs devices={[activeDevice, inactiveDevice]} selectedDeviceId={1} onSelect={onSelect} />
    );

    fireEvent.click(screen.getByText('monitor.power.total'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
