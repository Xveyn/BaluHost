import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
  }),
}));

vi.mock('../../../api/bluetooth', async () => {
  const actual = await vi.importActual<typeof import('../../../api/bluetooth')>('../../../api/bluetooth');
  return {
    ...actual,
    getBluetoothState: vi.fn(),
    setAdapterPowered: vi.fn().mockResolvedValue(undefined),
    startScan: vi.fn().mockResolvedValue(new Date(Date.now() + 30000).toISOString()),
    connectDevice: vi.fn().mockResolvedValue(undefined),
    disconnectDevice: vi.fn().mockResolvedValue(undefined),
    removeDevice: vi.fn().mockResolvedValue(undefined),
    startPairing: vi.fn().mockResolvedValue('s1'),
    getPairingSession: vi.fn().mockResolvedValue(null),
    answerPairing: vi.fn().mockResolvedValue(undefined),
    cancelPairing: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { BluetoothMenu } from '../../../components/topbar/BluetoothMenu';
import {
  disconnectDevice,
  getBluetoothState,
  getPairingSession,
  removeDevice,
  startPairing,
} from '../../../api/bluetooth';
import { getMyPowerPermissions } from '../../../api/powerPermissions';

const STATE = {
  available: true, detail: null, warning: null, can_pair_here: true, pairing_active: false,
  adapter: { address: 'AA:AA:AA:AA:AA:01', name: 'BaluNode', powered: true, discovering: false },
  devices: [
    { address: 'AA:AA:AA:AA:AA:02', name: 'Xbox Wireless Controller', kind: 'controller', icon: 'input-gaming',
      paired: true, trusted: true, connected: true, battery_percent: 80, rssi: null },
    { address: 'AA:AA:AA:AA:AA:03', name: 'JBL TUNE510BT', kind: 'audio', icon: 'audio-headphones',
      paired: true, trusted: true, connected: false, battery_percent: null, rssi: null },
    { address: 'AA:AA:AA:AA:AA:04', name: 'Dev-Tastatur', kind: 'input', icon: 'input-keyboard',
      paired: false, trusted: false, connected: false, battery_percent: null, rssi: -55 },
  ],
};

beforeEach(() => {
  vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_bluetooth: true } as never);
  vi.mocked(getBluetoothState).mockResolvedValue(structuredClone(STATE) as never);
});

async function open() {
  render(<BluetoothMenu />);
  fireEvent.click(await screen.findByLabelText('bluetooth:title'));
  await screen.findByText('Xbox Wireless Controller');
}

describe('BluetoothMenu', () => {
  it('bleibt unsichtbar ohne das Recht', async () => {
    vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_bluetooth: false } as never);
    const { container } = render(<BluetoothMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('fragt erst ab, wenn das Popover offen ist', async () => {
    vi.mocked(getBluetoothState).mockClear();
    render(<BluetoothMenu />);
    await screen.findByLabelText('bluetooth:title');
    expect(getBluetoothState).not.toHaveBeenCalled();
  });

  it('gruppiert gekoppelte Geraete nach Art und zeigt den Akku', async () => {
    await open();
    expect(screen.getByText('bluetooth:kind.controller')).toBeTruthy();
    expect(screen.getByText('bluetooth:kind.audio')).toBeTruthy();
    expect(screen.getByText('bluetooth:battery:80')).toBeTruthy();
  });

  it('trennt ein verbundenes Geraet', async () => {
    await open();
    fireEvent.click(screen.getByText('bluetooth:disconnect'));
    await waitFor(() => expect(disconnectDevice).toHaveBeenCalledWith('AA:AA:AA:AA:AA:02'));
  });

  it('entfernt nur nach Rueckfrage', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await open();
    fireEvent.click(screen.getByLabelText('bluetooth:remove: JBL TUNE510BT'));
    expect(removeDevice).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByLabelText('bluetooth:remove: JBL TUNE510BT'));
    await waitFor(() => expect(removeDevice).toHaveBeenCalledWith('AA:AA:AA:AA:AA:03'));
    confirm.mockRestore();
  });

  it('sperrt Koppeln ausserhalb des LANs mit Hinweis', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({ ...structuredClone(STATE), can_pair_here: false } as never);
    await open();
    const pair = screen.getByText('bluetooth:pair').closest('button') as HTMLButtonElement;
    expect(pair.disabled).toBe(true);
    expect(screen.getByText('bluetooth:pairOnlyLocal')).toBeTruthy();
  });

  it('sperrt Koppeln, waehrend jemand anderes koppelt', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({ ...structuredClone(STATE), pairing_active: true } as never);
    await open();
    expect((screen.getByText('bluetooth:pair').closest('button') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('bluetooth:pairBusy')).toBeTruthy();
  });

  it('startet eine Kopplung und oeffnet den Dialog', async () => {
    vi.mocked(getPairingSession).mockResolvedValue({
      session_id: 's1', address: 'AA:AA:AA:AA:AA:04', device_name: 'Dev-Tastatur',
      stage: 'connecting', code: null, entered: null, error: null,
    } as never);
    await open();
    fireEvent.click(screen.getByText('bluetooth:pair'));
    await waitFor(() => expect(startPairing).toHaveBeenCalledWith('AA:AA:AA:AA:AA:04'));
    expect(await screen.findByText('bluetooth:dialog.connecting')).toBeTruthy();
  });

  it('meldet ein nicht verfuegbares Bluetooth statt einer leeren Liste', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({
      ...structuredClone(STATE), available: false, adapter: null, devices: [], detail: 'Kein Adapter',
    } as never);
    render(<BluetoothMenu />);
    fireEvent.click(await screen.findByLabelText('bluetooth:title'));
    expect(await screen.findByText(/bluetooth:unavailable/)).toBeTruthy();
  });
});
