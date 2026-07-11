import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MobileDevice } from '../../api/mobile';

const hookState: Record<string, unknown> = {};
vi.mock('../../hooks/useMobileRegistration', () => ({
  useMobileRegistration: () => hookState,
}));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ isAdmin: true }) }));
vi.mock('../../components/mobile-devices', () => ({
  RegisterDeviceCard: () => <div>register-card</div>,
  MobileDevicesList: ({ devices }: { devices: MobileDevice[] }) => <div>list:{devices.length}</div>,
  QrCodeDialog: () => <div>qr-dialog</div>,
}));
import MobileDevicesPage from '../../pages/MobileDevicesPage';

function setHook(over: Record<string, unknown> = {}) {
  Object.assign(hookState, {
    devices: [], loading: false, isFetching: false, availableVpnTypes: [],
    deviceName: '', setDeviceName: vi.fn(), tokenValidityDays: 90, setTokenValidityDays: vi.fn(),
    includeVpn: false, setIncludeVpn: vi.fn(), vpnType: 'auto', setVpnType: vi.fn(), generating: false,
    showQrDialog: false, qrData: null, selectedDevice: null, showToken: false, toggleShowToken: vi.fn(),
    handleGenerateToken: vi.fn(), handleDeleteDevice: vi.fn(), handleShowDeviceQr: vi.fn(),
    refetchDevices: vi.fn(), closeQrDialog: vi.fn(), dialog: null, ...over,
  });
}

describe('MobileDevicesPage', () => {
  it('renders header, register card and list', () => {
    setHook({ devices: [{ id: 'd1' } as MobileDevice] });
    render(<MobileDevicesPage />);
    expect(screen.getByText('Mobile Geräte')).toBeInTheDocument();
    expect(screen.getByText('register-card')).toBeInTheDocument();
    expect(screen.getByText('list:1')).toBeInTheDocument();
  });
  it('does not render the dialog when showQrDialog is false', () => {
    setHook();
    render(<MobileDevicesPage />);
    expect(screen.queryByText('qr-dialog')).not.toBeInTheDocument();
  });
  it('renders the dialog when showQrDialog and qrData are set', () => {
    setHook({ showQrDialog: true, qrData: { token: 't' } });
    render(<MobileDevicesPage />);
    expect(screen.getByText('qr-dialog')).toBeInTheDocument();
  });
});
