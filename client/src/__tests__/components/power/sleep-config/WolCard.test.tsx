import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WolCard } from '../../../../components/power/sleep-config/WolCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps = (own: string | null): SleepCapabilities => ({
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: [], data_disk_devices: [], own_mac_address: own,
});

const base = { wolMac: '', wolBroadcast: '', update: vi.fn(), capabilities: caps(null) };

describe('WolCard', () => {
  it('renders the two address inputs', () => {
    render(<WolCard {...base} />);
    expect(screen.getByText('MAC Address')).toBeInTheDocument();
    expect(screen.getByText('Broadcast Address')).toBeInTheDocument();
  });

  it('offers the detected MAC when it differs from the current value', () => {
    const update = vi.fn();
    render(<WolCard {...base} capabilities={caps('DE:AD:BE:EF:00:01')} update={update} />);
    // accessible name spans split text nodes ("Erkannt: <mac> — Übernehmen?"); match by role+name regex
    fireEvent.click(screen.getByRole('button', { name: /Übernehmen/ }));
    expect(update).toHaveBeenCalledWith({ wolMac: 'DE:AD:BE:EF:00:01' });
  });

  it('does not offer the detected MAC when it already matches', () => {
    render(<WolCard {...base} wolMac="DE:AD:BE:EF:00:01" capabilities={caps('DE:AD:BE:EF:00:01')} />);
    expect(screen.queryByRole('button', { name: /Übernehmen/ })).toBeNull();
  });

  it('editing the MAC input calls update', () => {
    const update = vi.fn();
    render(<WolCard {...base} update={update} />);
    fireEvent.change(screen.getByPlaceholderText('AA:BB:CC:DD:EE:FF'), { target: { value: '01:02:03:04:05:06' } });
    expect(update).toHaveBeenCalledWith({ wolMac: '01:02:03:04:05:06' });
  });
});
