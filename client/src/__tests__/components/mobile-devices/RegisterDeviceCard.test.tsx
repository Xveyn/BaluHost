import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RegisterDeviceCard } from '../../../components/mobile-devices/RegisterDeviceCard';

const base = {
  deviceName: '', onDeviceNameChange: vi.fn(),
  tokenValidityDays: 90, onValidityChange: vi.fn(),
  includeVpn: false, onIncludeVpnChange: vi.fn(),
  vpnType: 'auto', onVpnTypeChange: vi.fn(),
  availableVpnTypes: ['wireguard'], generating: false, onGenerate: vi.fn(),
};

describe('RegisterDeviceCard', () => {
  it('typing a name fires onDeviceNameChange', () => {
    const onDeviceNameChange = vi.fn();
    render(<RegisterDeviceCard {...base} onDeviceNameChange={onDeviceNameChange} />);
    fireEvent.change(screen.getByPlaceholderText('z.B. iPhone 15, Samsung Galaxy S24'), { target: { value: 'X' } });
    expect(onDeviceNameChange).toHaveBeenCalledWith('X');
  });
  it('generate button is disabled when name blank', () => {
    render(<RegisterDeviceCard {...base} />);
    expect(screen.getByText('QR-Code generieren').closest('button')).toBeDisabled();
  });
  it('generate fires onGenerate when name present', () => {
    const onGenerate = vi.fn();
    render(<RegisterDeviceCard {...base} deviceName="iPhone" onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText('QR-Code generieren').closest('button')!);
    expect(onGenerate).toHaveBeenCalled();
  });
  it('shows VPN type selector only when >1 vpn types and includeVpn', () => {
    const { rerender } = render(<RegisterDeviceCard {...base} includeVpn availableVpnTypes={['wireguard']} />);
    expect(screen.queryByText('Automatisch')).not.toBeInTheDocument();
    rerender(<RegisterDeviceCard {...base} includeVpn availableVpnTypes={['fritzbox', 'wireguard']} />);
    expect(screen.getByText('Automatisch')).toBeInTheDocument();
    fireEvent.click(screen.getByText('NAS-VPN (WireGuard)'));
    expect(base.onVpnTypeChange).toHaveBeenCalledWith('wireguard');
  });
});
