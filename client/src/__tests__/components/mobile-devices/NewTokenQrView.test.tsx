import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileRegistrationToken } from '../../../api/mobile';

const success = vi.fn();
vi.mock('react-hot-toast', () => ({ default: { success: (...a: unknown[]) => success(...a) } }));
import { NewTokenQrView } from '../../../components/mobile-devices/NewTokenQrView';

const token = (over: Partial<MobileRegistrationToken> = {}): MobileRegistrationToken => ({
  token: 'tok-abc', qr_code: 'iVBORpng', expires_at: '2026-06-01T12:00:00Z',
  device_token_validity_days: 90, vpn_config: null, vpn_fallback: false,
  ...over,
} as MobileRegistrationToken);

describe('NewTokenQrView', () => {
  it('toggle button fires onToggleToken', () => {
    const onToggleToken = vi.fn();
    render(<NewTokenQrView qrData={token()} showToken={false} onToggleToken={onToggleToken} />);
    fireEvent.click(screen.getByText('Token manuell anzeigen'));
    expect(onToggleToken).toHaveBeenCalled();
  });
  it('shows the token and copies on click when showToken', () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
    render(<NewTokenQrView qrData={token()} showToken onToggleToken={vi.fn()} />);
    expect(screen.getByText('tok-abc')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Kopieren'));
    expect(success).toHaveBeenCalledWith('Token kopiert');
  });
  it('uses image/png src prefix when qr_code starts with iVBOR', () => {
    render(<NewTokenQrView qrData={token({ qr_code: 'iVBORxyz' })} showToken={false} onToggleToken={vi.fn()} />);
    expect(screen.getByAltText('QR Code').getAttribute('src')).toContain('data:image/png;base64,iVBORxyz');
  });
  it('uses image/svg+xml when qr_code does not start with iVBOR', () => {
    render(<NewTokenQrView qrData={token({ qr_code: 'PHN2Zz' })} showToken={false} onToggleToken={vi.fn()} />);
    expect(screen.getByAltText('QR Code').getAttribute('src')).toContain('data:image/svg+xml;base64,PHN2Zz');
  });
});
