import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileRegistrationToken, MobileDevice } from '../../../api/mobile';

vi.mock('../../../components/mobile-devices/NewTokenQrView', () => ({
  NewTokenQrView: () => <div>new-token-view</div>,
}));
vi.mock('../../../components/mobile-devices/ExistingDeviceInfoView', () => ({
  ExistingDeviceInfoView: () => <div>existing-device-view</div>,
}));
import { QrCodeDialog } from '../../../components/mobile-devices/QrCodeDialog';

const token = { token: 't', qr_code: 'iVBOR', expires_at: '2026-01-01T00:00:00Z', device_token_validity_days: 90 } as MobileRegistrationToken;
const device = { id: 'd1', device_name: 'iPhone' } as MobileDevice;
const base = { isAdmin: false, showToken: false, onToggleToken: vi.fn(), onClose: vi.fn() };

describe('QrCodeDialog', () => {
  it('renders new-token header and view when qrData is set', () => {
    render(<QrCodeDialog {...base} qrData={token} selectedDevice={null} />);
    expect(screen.getByText('QR-Code für Mobile App')).toBeInTheDocument();
    expect(screen.getByText('new-token-view')).toBeInTheDocument();
  });
  it('renders existing-device header and view when only selectedDevice is set', () => {
    render(<QrCodeDialog {...base} qrData={null} selectedDevice={device} />);
    expect(screen.getByText('QR-Code: iPhone')).toBeInTheDocument();
    expect(screen.getByText('existing-device-view')).toBeInTheDocument();
  });
  it('close button fires onClose', () => {
    const onClose = vi.fn();
    render(<QrCodeDialog {...base} qrData={token} selectedDevice={null} onClose={onClose} />);
    fireEvent.click(screen.getByText('✕'));
    expect(onClose).toHaveBeenCalled();
  });
});
