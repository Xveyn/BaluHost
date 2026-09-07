import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import FirmwareFanNotice from '../../../components/fan-control/FirmwareFanNotice';

// `t` gibt den Schluessel zurueck; Interpolationswerte werden angehaengt,
// damit ein Text wie "…writeFailed" mit {{nodes}} im DOM pruefbar bleibt,
// ohne echte Locale-Dateien zu laden.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      (opts && Object.keys(opts).length ? `${k}|${Object.values(opts).join(',')}` : k),
  }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

const setGpuManualMode = vi.fn();
vi.mock('../../../api/fan-control', () => ({
  setGpuManualMode: (...args: unknown[]) => setGpuManualMode(...args),
  // Default: no acoustics interface on this card — keeps the pre-existing
  // manual-mode tests below unaffected by the (unrelated) useEffect fetch.
  getGpuAcoustics: vi.fn().mockResolvedValue({
    available: false,
    competing_manager: null,
    nodes: {},
  }),
  setGpuAcoustics: vi.fn(),
}));

import toast from 'react-hot-toast';
import { getGpuAcoustics, setGpuAcoustics } from '../../../api/fan-control';

describe('FirmwareFanNotice: Ausstieg aus dem manuellen Modus bleibt erreichbar', () => {
  it('bietet einen Reset-Button, der setGpuManualMode(fanId, false) aufruft', async () => {
    setGpuManualMode.mockResolvedValueOnce(undefined);
    render(<FirmwareFanNotice fanId="gpu_pwm1" />);

    fireEvent.click(screen.getByText('system:fanControl.gpu.firmware.resetButton'));

    await waitFor(() => {
      expect(setGpuManualMode).toHaveBeenCalledWith('gpu_pwm1', false);
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('meldet einen Fehler ueber handleApiError, statt ihn zu verschlucken', async () => {
    setGpuManualMode.mockRejectedValueOnce(new Error('boom'));
    render(<FirmwareFanNotice fanId="gpu_pwm1" />);

    fireEvent.click(screen.getByText('system:fanControl.gpu.firmware.resetButton'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});

const STATUS = {
  available: true,
  competing_manager: null as string | null,
  nodes: {
    fan_target_temperature: { current: 95, minimum: 25, maximum: 105, desired: null },
  },
};

it('zeigt einen Regler je gemeldetem Knoten, mit den Grenzen des Treibers', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const slider = await screen.findByRole('slider', { name: /fan_target_temperature/ });
  expect((slider as HTMLInputElement).min).toBe('25');
  expect((slider as HTMLInputElement).max).toBe('105');
});

it('nennt Zero-RPM, damit ein wirkungsloser Regler nicht wie ein Defekt aussieht', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  expect(await screen.findByTestId('gpu-acoustics-zero-rpm-hint')).toBeTruthy();
});

it('warnt vor einem zweiten Verwalter', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({ ...STATUS, competing_manager: 'lact' });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  expect(await screen.findByTestId('gpu-acoustics-competing')).toBeTruthy();
});

it('blendet sich aus, wenn die Karte die Schnittstelle nicht hat', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({ ...STATUS, available: false, nodes: {} });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  await waitFor(() =>
    expect(screen.queryByRole('slider')).toBeNull());
});

it('Reset ruft setGpuAcoustics mit null fuer jeden Knoten auf, und die Regler zeigen danach die Antwort statt des alten Stands', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  const restored = {
    available: true,
    competing_manager: null as string | null,
    nodes: {
      fan_target_temperature: { current: 60, minimum: 25, maximum: 105, desired: null },
    },
  };
  vi.mocked(setGpuAcoustics).mockResolvedValue(restored);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const slider = await screen.findByRole('slider', { name: /fan_target_temperature/ });
  expect((slider as HTMLInputElement).value).toBe('95');

  fireEvent.click(screen.getByText('system:fanControl.gpu.acoustics.reset'));

  await waitFor(() => {
    expect(setGpuAcoustics).toHaveBeenCalledWith({ fan_target_temperature: null });
  });

  await waitFor(() => {
    expect((screen.getByRole('slider', { name: /fan_target_temperature/ }) as HTMLInputElement).value)
      .toBe('60');
  });
});

it('deaktiviert Save und Reset, solange eine Anfrage laeuft', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  let resolveSet: (value: typeof STATUS) => void = () => {};
  vi.mocked(setGpuAcoustics).mockReturnValue(
    new Promise<typeof STATUS>((resolve) => { resolveSet = resolve; }),
  );
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const saveButton = await screen.findByText('system:fanControl.gpu.acoustics.save');
  const resetButton = screen.getByText('system:fanControl.gpu.acoustics.reset');
  expect(saveButton).not.toBeDisabled();

  fireEvent.click(saveButton);

  await waitFor(() => {
    expect(saveButton).toBeDisabled();
    expect(resetButton).toBeDisabled();
  });

  resolveSet(STATUS);

  await waitFor(() => {
    expect(saveButton).not.toBeDisabled();
    expect(resetButton).not.toBeDisabled();
  });
});

// --- Befund A/B/C aus dem Abschluss-Review ---------------------------------

const FOUR_NODES = {
  fan_target_temperature: { current: 95, minimum: 25, maximum: 105, desired: null as number | null },
  acoustic_limit_rpm_threshold: { current: 3000, minimum: 500, maximum: 3200, desired: null as number | null },
  acoustic_target_rpm_threshold: { current: 2200, minimum: 500, maximum: 3200, desired: null as number | null },
  fan_minimum_pwm: { current: 20, minimum: 0, maximum: 100, desired: null as number | null },
};

const FULL_STATUS = {
  available: true,
  competing_manager: null as string | null,
  nodes: FOUR_NODES,
  writes: {} as Record<string, { ok: boolean; value: number; restored?: boolean }>,
};

it('zeigt den aktuellen Wert der Karte je Knoten an, nicht nur den Entwurf', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const readout = await screen.findByTestId('gpu-acoustics-current-fan_target_temperature');
  expect(readout.textContent).toContain('95');
  expect(
    (await screen.findByTestId('gpu-acoustics-current-acoustic_limit_rpm_threshold')).textContent,
  ).toContain('3000');
});

it('meldet einen von der Karte abgelehnten Write, statt Erfolg zu behaupten', async () => {
  // Die Toast-Mocks werden zwischen den Tests dieser Datei nicht
  // zurueckgesetzt; ohne mockClear zaehlte hier der Erfolg eines
  // frueheren Tests mit.
  vi.mocked(toast.success).mockClear();
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  vi.mocked(setGpuAcoustics).mockResolvedValue({
    ...FULL_STATUS,
    writes: {
      fan_target_temperature: { ok: true, value: 78 },
      acoustic_limit_rpm_threshold: { ok: false, value: 3000 },
    },
  });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  fireEvent.click(await screen.findByText('system:fanControl.gpu.acoustics.save'));

  const error = await screen.findByTestId('gpu-acoustics-error');
  expect(error.textContent).toContain('acoustic_limit_rpm_threshold');
  expect(error.textContent).not.toContain('fan_minimum_pwm');
  expect(toast.success).not.toHaveBeenCalled();
});

it('meldet eine 503 als Konfigurationsproblem, nicht als Hardware-Fehler', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  vi.mocked(setGpuAcoustics).mockRejectedValue({
    response: { status: 503, data: { detail: 'GPU acoustics configuration is currently unreadable' } },
  });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  fireEvent.click(await screen.findByText('system:fanControl.gpu.acoustics.save'));

  const error = await screen.findByTestId('gpu-acoustics-error');
  expect(error.textContent).toContain('configUnavailable');
});

it('haelt einen Knoten ohne desired als nicht verwaltet: Regler gesperrt, Markierung leer', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const box = await screen.findByRole('checkbox', { name: /fan_target_temperature/ });
  expect((box as HTMLInputElement).checked).toBe(false);
  expect(screen.getByRole('slider', { name: /fan_target_temperature/ })).toBeDisabled();
});

it('zeigt einen bereits verwalteten Knoten als markiert und bedienbar', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({
    ...FULL_STATUS,
    nodes: {
      ...FOUR_NODES,
      fan_target_temperature: { current: 95, minimum: 25, maximum: 105, desired: 78 },
    },
  });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const box = await screen.findByRole('checkbox', { name: /fan_target_temperature/ });
  expect((box as HTMLInputElement).checked).toBe(true);
  const slider = screen.getByRole('slider', { name: /fan_target_temperature/ });
  expect(slider).not.toBeDisabled();
  expect((slider as HTMLInputElement).value).toBe('78');
});

it('sendet fuer nicht markierte Knoten null: nur die Zieltemperatur wird verwaltet', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  vi.mocked(setGpuAcoustics).mockResolvedValue(FULL_STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const box = await screen.findByRole('checkbox', { name: /fan_target_temperature/ });
  fireEvent.click(box);

  const slider = screen.getByRole('slider', { name: /fan_target_temperature/ });
  expect(slider).not.toBeDisabled();
  fireEvent.change(slider, { target: { value: '78' } });

  expect(screen.getByRole('slider', { name: /acoustic_limit_rpm_threshold/ })).toBeDisabled();

  fireEvent.click(screen.getByText('system:fanControl.gpu.acoustics.save'));

  await waitFor(() => {
    expect(setGpuAcoustics).toHaveBeenCalledWith({
      fan_target_temperature: 78,
      acoustic_limit_rpm_threshold: null,
      acoustic_target_rpm_threshold: null,
      fan_minimum_pwm: null,
    });
  });
});

it('laesst einen Knoten aus, den der PUT gar nicht setzen kann (Kernel 6.13)', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({
    ...FULL_STATUS,
    nodes: {
      ...FOUR_NODES,
      fan_zero_rpm_enable: { current: 1, minimum: 0, maximum: 1, desired: null },
      fan_zero_rpm_stop_temperature: { current: 55, minimum: 25, maximum: 100, desired: null },
    },
  });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  await screen.findByRole('slider', { name: /fan_target_temperature/ });
  expect(screen.queryByRole('slider', { name: /fan_zero_rpm_enable/ })).toBeNull();
  expect(screen.queryByRole('slider', { name: /fan_zero_rpm_stop_temperature/ })).toBeNull();
  expect(screen.queryAllByRole('slider')).toHaveLength(4);
  expect(document.body.textContent).not.toContain('fan_zero_rpm');
});
