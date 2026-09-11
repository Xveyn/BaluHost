import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LayoutHeader } from '../../../components/layout/LayoutHeader';

const featureState = vi.hoisted(() => ({ isPi: false }));
vi.mock('../../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));
vi.mock('../../../components/NotificationCenter', () => ({ default: () => <div data-testid="notification-center" /> }));
vi.mock('../../../components/PowerMenu', () => ({ default: () => <div data-testid="power-menu" /> }));
vi.mock('../../../components/UserMenu', () => ({ default: () => <div data-testid="user-menu" /> }));
vi.mock('../../../components/topbar/TopbarStatusStrip', () => ({ TopbarStatusStrip: () => <div data-testid="topbar-status-strip" /> }));

// audioEnabled ist per-Test umschaltbar - das ist die Nahtstelle des Defekts:
// usePluginEnabled('audio_control') war dauerhaft false, weil das Plugin nie
// im UI-Manifest auftauchte (siehe AudioControlPlugin.get_ui_manifest()).
const pluginState = vi.hoisted(() => ({ audioEnabled: false, bluetoothEnabled: false }));
vi.mock('../../../contexts/PluginContext', () => ({
  usePluginEnabled: (name: string) =>
    (name === 'audio_control' && pluginState.audioEnabled) ||
    (name === 'bluetooth' && pluginState.bluetoothEnabled),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

// LayoutHeader rendert AudioMenu ungemockt (anders als PowerMenu/UserMenu/...),
// damit der Test den echten Knopf sieht statt eines Platzhalter-divs. AudioMenu
// zieht selbst API-Module - die muessen wie in AudioMenu.test.tsx gemockt werden,
// sonst schlaegt der ungemockte axios-Aufruf in jsdom fehl.
vi.mock('../../../api/audioControl', () => ({
  getAudioState: vi.fn().mockResolvedValue({ available: true, detail: null, sinks: [], streams: [] }),
  setSinkVolume: vi.fn().mockResolvedValue(undefined),
  setSinkMute: vi.fn().mockResolvedValue(undefined),
  setDefaultSink: vi.fn().mockResolvedValue(undefined),
  setStreamVolume: vi.fn().mockResolvedValue(undefined),
  setStreamMute: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../../api/bluetooth', () => ({
  TERMINAL_STAGES: new Set(['succeeded', 'failed', 'cancelled']),
  getBluetoothState: vi.fn().mockResolvedValue({ available: false, detail: null, warning: null, adapter: null, devices: [], can_pair_here: false, pairing_active: false }),
  setAdapterPowered: vi.fn(), startScan: vi.fn(), connectDevice: vi.fn(), disconnectDevice: vi.fn(),
  removeDevice: vi.fn(), startPairing: vi.fn(), getPairingSession: vi.fn().mockResolvedValue(null),
  answerPairing: vi.fn(), cancelPairing: vi.fn(),
}));
vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn().mockResolvedValue({ can_control_audio: true, can_manage_bluetooth: true }),
}));

const props = {
  isImpersonating: false,
  isAdmin: true,
  onOpenMobileMenu: vi.fn(),
  onShutdown: vi.fn(),
  onRestart: vi.fn(),
  onLogout: vi.fn(),
};

beforeEach(() => {
  featureState.isPi = false;
  pluginState.audioEnabled = false;
  pluginState.bluetoothEnabled = false;
});

describe('LayoutHeader', () => {
  it('Standard: PowerMenu + NotificationCenter + StatusStrip, kein Pi-Logout-Button', () => {
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByTestId('topbar-status-strip')).toBeInTheDocument();
    expect(screen.queryByTitle('Logout')).not.toBeInTheDocument();
  });

  it('audio_control deaktiviert: kein Lautsprecher-Symbol in der Topbar', () => {
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: 'title' })).not.toBeInTheDocument();
  });

  it('audio_control aktiviert: Lautsprecher-Symbol erscheint (Regression fuer das fehlende UI-Manifest)', async () => {
    pluginState.audioEnabled = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'title' })).toBeInTheDocument(),
    );
  });

  it('bluetooth aktiviert: Bluetooth-Symbol erscheint', async () => {
    pluginState.bluetoothEnabled = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'title' })).toBeInTheDocument(),
    );
  });

  it('Pi: Logout-Button statt PowerMenu, kein NotificationCenter/StatusStrip', () => {
    featureState.isPi = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTitle('Logout')).toBeInTheDocument();
    expect(screen.queryByTestId('power-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('notification-center')).not.toBeInTheDocument();
    expect(screen.queryByTestId('topbar-status-strip')).not.toBeInTheDocument();
  });

  it('Impersonation: header top-10', () => {
    const { container } = render(<MemoryRouter><LayoutHeader {...props} isImpersonating /></MemoryRouter>);
    expect(container.querySelector('header')!.className).toContain('top-10');
  });
});
