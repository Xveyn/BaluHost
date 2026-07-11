import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../components/mobile-devices/NotificationStatus', () => ({
  NotificationStatus: () => null,
}));
import { MobileDeviceCard } from '../../../components/mobile-devices/MobileDeviceCard';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-1', device_name: 'iPhone 15', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null,
  device_model: null, os_version: null, app_version: null,
  last_sync: null, last_seen: null, username: null,
  ...over,
} as MobileDevice);

describe('MobileDeviceCard', () => {
  it('shows the device name and Aktiv when active', () => {
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('iPhone 15')).toBeInTheDocument();
    expect(screen.getByText('Aktiv')).toBeInTheDocument();
  });

  it('shows Abgelaufen badge for a past expiry', () => {
    const past = new Date(Date.now() - 5 * 86_400_000).toISOString();
    render(<MobileDeviceCard device={device({ expires_at: past })} isAdmin={false} onShowQr={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('Abgelaufen')).toBeInTheDocument();
  });

  it('delete button fires onDelete and not onShowQr (stopPropagation)', () => {
    const onShowQr = vi.fn();
    const onDelete = vi.fn();
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={onShowQr} onDelete={onDelete} />);
    fireEvent.click(screen.getByTitle('Gerät löschen'));
    expect(onDelete).toHaveBeenCalledWith('dev-1', 'iPhone 15');
    expect(onShowQr).not.toHaveBeenCalled();
  });

  it('card click fires onShowQr', () => {
    const onShowQr = vi.fn();
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={onShowQr} onDelete={vi.fn()} />);
    fireEvent.click(screen.getByTitle('Klicken um QR-Code anzuzeigen'));
    expect(onShowQr).toHaveBeenCalled();
  });
});
