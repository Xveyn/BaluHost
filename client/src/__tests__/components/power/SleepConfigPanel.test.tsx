import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/sleep', () => ({
  getSleepConfig: vi.fn(),
  getSleepCapabilities: vi.fn(),
  getSleepStatus: vi.fn(),
  updateSleepConfig: vi.fn(),
}));
vi.mock('../../../api/fritzbox', () => ({
  getFritzBoxConfig: vi.fn(),
  updateFritzBoxConfig: vi.fn(),
  testFritzBoxConnection: vi.fn(),
}));

import { getSleepConfig, getSleepCapabilities, getSleepStatus, updateSleepConfig } from '../../../api/sleep';
import { getFritzBoxConfig, updateFritzBoxConfig } from '../../../api/fritzbox';
import type { SleepConfigResponse, SleepCapabilities } from '../../../api/sleep';
import { SleepConfigPanel } from '../../../components/power/SleepConfigPanel';

const config: SleepConfigResponse = {
  auto_idle_enabled: true, idle_timeout_minutes: 15, idle_cpu_threshold: 5,
  idle_disk_io_threshold: 0.5, idle_http_threshold: 5,
  auto_escalation_enabled: false, escalation_after_minutes: 60,
  schedule_enabled: false, schedule_sleep_time: '23:00', schedule_wake_time: '06:00',
  schedule_mode: 'soft', wol_mac_address: null, wol_broadcast_address: null,
  pause_monitoring: true, pause_disk_io: true, reduced_telemetry_interval: 30,
  disk_spindown_enabled: true, core_uptime_enabled: false, core_uptime_suspend_on_exit: false,
  presence_enabled: true, presence_mode: 'active', presence_timeout_minutes: 3,
};
const caps: SleepCapabilities = {
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: ['eth0'], data_disk_devices: ['sda'], own_mac_address: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getSleepConfig as any).mockResolvedValue(config);
  (getSleepCapabilities as any).mockResolvedValue(caps);
  (getSleepStatus as any).mockResolvedValue({ core_uptime: { enabled: false }, always_awake: { enabled: false }, presence: null });
  (getFritzBoxConfig as any).mockResolvedValue({ host: '192.168.178.1', port: 49000, username: '', nas_mac_address: null, enabled: false, has_password: false });
  (updateSleepConfig as any).mockResolvedValue(config);
  (updateFritzBoxConfig as any).mockResolvedValue(undefined);
});

describe('SleepConfigPanel (integration)', () => {
  it('loads config, seeds the form, and saves the edited payload', async () => {
    render(<SleepConfigPanel />);

    // after load: capabilities card + save button visible
    await waitFor(() => expect(screen.getByText('System Capabilities')).toBeInTheDocument());
    expect(screen.getByText('Save Configuration')).toBeInTheDocument();

    // idle detection was seeded enabled -> its inputs are visible; edit the timeout
    const timeout = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(timeout, { target: { value: '25' } });

    fireEvent.click(screen.getByText('Save Configuration'));

    await waitFor(() => expect(updateSleepConfig).toHaveBeenCalledTimes(1));
    const payload = (updateSleepConfig as any).mock.calls[0][0];
    expect(payload.idle_timeout_minutes).toBe(25);
    expect(payload.wol_mac_address).toBeNull();          // empty -> null mapping preserved
    expect(payload.presence_mode).toBe('active');
    expect(updateFritzBoxConfig).toHaveBeenCalledTimes(1);
  });
});
