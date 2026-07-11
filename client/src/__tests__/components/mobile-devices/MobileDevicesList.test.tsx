import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';

vi.mock('../../../components/mobile-devices/MobileDeviceCard', () => ({
  MobileDeviceCard: ({ device }: { device: MobileDevice }) => <div>card:{device.device_name}</div>,
}));
import { MobileDevicesList } from '../../../components/mobile-devices/MobileDevicesList';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-1', device_name: 'iPhone 15', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null,
  ...over,
} as MobileDevice);

const base = { isAdmin: false, onRefresh: vi.fn(), onShowQr: vi.fn(), onDelete: vi.fn() };

describe('MobileDevicesList', () => {
  it('shows loading state', () => {
    render(<MobileDevicesList devices={[]} loading isFetching={false} {...base} />);
    expect(screen.getByText('Lade Geräte...')).toBeInTheDocument();
  });
  it('shows empty state', () => {
    render(<MobileDevicesList devices={[]} loading={false} isFetching={false} {...base} />);
    expect(screen.getByText('Keine Geräte registriert')).toBeInTheDocument();
  });
  it('renders a card per device and count', () => {
    render(<MobileDevicesList devices={[device(), device({ id: 'dev-2', device_name: 'Pixel' })]} loading={false} isFetching={false} {...base} />);
    expect(screen.getByText('card:iPhone 15')).toBeInTheDocument();
    expect(screen.getByText('card:Pixel')).toBeInTheDocument();
    expect(screen.getByText('Registrierte Geräte (2)')).toBeInTheDocument();
  });
  it('refresh button fires onRefresh', () => {
    const onRefresh = vi.fn();
    render(<MobileDevicesList devices={[]} loading={false} isFetching={false} {...base} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByTitle('Aktualisieren'));
    expect(onRefresh).toHaveBeenCalled();
  });
});
