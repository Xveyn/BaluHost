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
    getPairingSession: vi.fn(),
    answerPairing: vi.fn().mockResolvedValue(undefined),
    cancelPairing: vi.fn().mockResolvedValue(undefined),
  };
});

import { BluetoothPairingDialog } from '../../../components/topbar/BluetoothPairingDialog';
import { answerPairing, cancelPairing, getPairingSession } from '../../../api/bluetooth';

function session(overrides: Record<string, unknown>) {
  return {
    session_id: 's1', address: 'AA:AA:AA:AA:AA:04', device_name: 'Dev-Tastatur',
    stage: 'connecting', code: null, entered: null, error: null, ...overrides,
  };
}

function renderDialog(kind: 'input' | 'audio' = 'input') {
  const onClose = vi.fn();
  render(
    <BluetoothPairingDialog sessionId="s1" deviceName="Dev-Tastatur" kind={kind} onClose={onClose} pollMs={10} />,
  );
  return onClose;
}

beforeEach(() => {
  vi.mocked(getPairingSession).mockReset();
});

describe('BluetoothPairingDialog', () => {
  it('zeigt den Code mit Fortschritt', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'display_passkey', code: '482913', entered: 2 }) as never,
    );
    renderDialog();
    expect((await screen.findByTestId('pairing-code')).textContent).toBe('482913');
    expect(screen.getByTestId('pairing-progress').textContent).toBe('●●○○○○');
  });

  it('bestaetigt einen Zahlenvergleich', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'confirm', code: '654321' }) as never,
    );
    renderDialog('audio');
    fireEvent.click(await screen.findByText('bluetooth:dialog.accept'));
    await waitFor(() => expect(answerPairing).toHaveBeenCalledWith('s1', true));
  });

  it('bricht ab', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(session({}) as never);
    renderDialog();
    fireEvent.click(await screen.findByText('bluetooth:dialog.cancel'));
    await waitFor(() => expect(cancelPairing).toHaveBeenCalledWith('s1'));
  });

  it('meldet abgebrochen, wenn die Sitzung ohne Endstand verschwindet', async () => {
    vi.mocked(getPairingSession)
      .mockResolvedValueOnce(session({}) as never)
      .mockResolvedValue(null as never);
    renderDialog();
    expect(await screen.findByText('bluetooth:dialog.cancelled')).toBeTruthy();
  });

  it('ignoriert eine fremde Sitzung', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ session_id: 'andere', stage: 'display_passkey', code: '111111', entered: 0 }) as never,
    );
    renderDialog();
    await waitFor(() => expect(getPairingSession).toHaveBeenCalled());
    expect(screen.queryByTestId('pairing-code')).toBeNull();
  });

  it('uebersetzt den Fehlerschluessel', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'failed', error: 'auth_failed' }) as never,
    );
    const onClose = renderDialog();
    expect(await screen.findByText('bluetooth:dialog.error.auth_failed')).toBeTruthy();
    fireEvent.click(screen.getByText('bluetooth:dialog.close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('warnt nur bei Eingabegeraeten', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(session({}) as never);
    renderDialog('input');
    expect(await screen.findByText('bluetooth:dialog.inputWarning')).toBeTruthy();
  });
});
