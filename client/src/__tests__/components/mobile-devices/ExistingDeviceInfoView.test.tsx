import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';
import { ExistingDeviceInfoView } from '../../../components/mobile-devices/ExistingDeviceInfoView';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-xyz', device_name: 'iPhone', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null, username: null,
  ...over,
} as MobileDevice);

describe('ExistingDeviceInfoView', () => {
  it('renders device id and origin', () => {
    render(<ExistingDeviceInfoView device={device()} isAdmin={false} />);
    expect(screen.getByText('dev-xyz')).toBeInTheDocument();
    expect(screen.getByText('Registriertes Gerät', { exact: false })).toBeInTheDocument();
  });
  it('shows Aktiv badge for a far-future expiry', () => {
    const future = new Date(Date.now() + 60 * 86_400_000).toISOString();
    render(<ExistingDeviceInfoView device={device({ expires_at: future })} isAdmin={false} />);
    expect(screen.getByText('Aktiv')).toBeInTheDocument();
  });
  it('shows Abgelaufen badge for a past expiry', () => {
    const past = new Date(Date.now() - 60 * 86_400_000).toISOString();
    render(<ExistingDeviceInfoView device={device({ expires_at: past })} isAdmin={false} />);
    expect(screen.getByText('Abgelaufen')).toBeInTheDocument();
  });
  it('shows the username row only when isAdmin', () => {
    const { rerender } = render(<ExistingDeviceInfoView device={device({ username: 'bob' })} isAdmin={false} />);
    expect(screen.queryByText('Benutzer:')).not.toBeInTheDocument();
    rerender(<ExistingDeviceInfoView device={device({ username: 'bob' })} isAdmin />);
    expect(screen.getByText('Benutzer:')).toBeInTheDocument();
  });
});
