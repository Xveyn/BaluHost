import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FritzBoxCard } from '../../../../components/power/sleep-config/FritzBoxCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps: SleepCapabilities = {
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: [], data_disk_devices: [], own_mac_address: null,
};
const base = {
  host: '192.168.178.1', port: 49000, username: '', password: '', mac: '', enabled: false,
  update: vi.fn(), config: null, testing: false, onTest: vi.fn(), capabilities: caps,
};

describe('FritzBoxCard', () => {
  it('hides the detail fields when disabled', () => {
    render(<FritzBoxCard {...base} enabled={false} />);
    expect(screen.queryByText('Host')).toBeNull();
  });

  it('shows detail fields + test button when enabled and fires onTest', () => {
    const onTest = vi.fn();
    render(<FritzBoxCard {...base} enabled onTest={onTest} />);
    expect(screen.getByText('Host')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Test Connection'));
    expect(onTest).toHaveBeenCalled();
  });

  it('disables the test button while testing', () => {
    render(<FritzBoxCard {...base} enabled testing />);
    expect(screen.getByText('Testing...').closest('button')).toBeDisabled();
  });

  it('editing host calls update', () => {
    const update = vi.fn();
    render(<FritzBoxCard {...base} enabled update={update} />);
    fireEvent.change(screen.getByPlaceholderText('192.168.178.1'), { target: { value: '10.0.0.1' } });
    expect(update).toHaveBeenCalledWith({ host: '10.0.0.1' });
  });
});
