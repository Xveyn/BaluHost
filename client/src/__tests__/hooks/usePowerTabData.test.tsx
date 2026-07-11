import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('../../api/smart-devices', () => ({ smartDevicesApi: { list: vi.fn(), getPowerSummary: vi.fn() } }));
vi.mock('../../api/energy', () => ({ getCumulativeEnergy: vi.fn(), getCumulativeEnergyTotal: vi.fn() }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => ({ plugins: [] }) }));

import { smartDevicesApi } from '../../api/smart-devices';
import { getCumulativeEnergyTotal } from '../../api/energy';
import { usePowerTabData } from '../../hooks/usePowerTabData';

const device = { id: 1, name: 'Plug', plugin_name: 'p', device_type_id: 't', address: 'a', mac_address: null, capabilities: ['power_monitor'], is_active: true, is_online: true, last_seen: null, last_error: null, state: null, created_at: '', updated_at: '' };

beforeEach(() => {
  vi.clearAllMocks();
  (smartDevicesApi.list as any).mockResolvedValue({ data: { devices: [device] } });
  (smartDevicesApi.getPowerSummary as any).mockResolvedValue({ data: { total_watts: 42 } });
  (getCumulativeEnergyTotal as any).mockResolvedValue({ device_id: 0, device_name: '', period: 'today', cost_per_kwh: 0.3, currency: 'EUR', total_kwh: 1, total_cost: 0.3, data_points: [] });
});

const base = { selectedDeviceId: null, cumulativePeriod: 'today' as const, customStart: null, customEnd: null };

describe('usePowerTabData', () => {
  it('exposes devices, totalCurrentPower and cumulative data', async () => {
    const { result } = renderHook(() => usePowerTabData(base), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.devices).toHaveLength(1);
    expect(result.current.totalCurrentPower).toBe(42);
    await waitFor(() => expect(result.current.cumulativeData?.total_kwh).toBe(1));
    expect(result.current.cumulativeReady).toBe(true);
  });

  it('cumulativeReady false for custom with no applied range', () => {
    const { result } = renderHook(() => usePowerTabData({ ...base, cumulativePeriod: 'custom' }), { wrapper: createQueryWrapper() });
    expect(result.current.cumulativeReady).toBe(false);
  });
});
