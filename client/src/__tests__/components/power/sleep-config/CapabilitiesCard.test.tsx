import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CapabilitiesCard } from '../../../../components/power/sleep-config/CapabilitiesCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps = (over: Partial<SleepCapabilities> = {}): SleepCapabilities => ({
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: ['eth0'], data_disk_devices: ['sda'],
  own_mac_address: 'AA:BB:CC:DD:EE:FF', ...over,
});

describe('CapabilitiesCard', () => {
  it('renders capability badges', () => {
    render(<CapabilitiesCard capabilities={caps()} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.getByText(/hdparm/)).toBeInTheDocument();
    expect(screen.getByText(/rtcwake/)).toBeInTheDocument();
  });

  it('shows Setup Help only when a capability is missing', () => {
    const { rerender } = render(<CapabilitiesCard capabilities={caps()} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.queryByText('Setup Help')).toBeNull(); // all present -> no help

    rerender(<CapabilitiesCard capabilities={caps({ hdparm_available: false })} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.getByText('Setup Help')).toBeInTheDocument();
  });

  it('fires onToggleHelp when the help button is clicked', () => {
    const onToggleHelp = vi.fn();
    render(<CapabilitiesCard capabilities={caps({ can_suspend: false })} helpOpen={false} onToggleHelp={onToggleHelp} />);
    fireEvent.click(screen.getByText('Setup Help'));
    expect(onToggleHelp).toHaveBeenCalled();
  });
});
