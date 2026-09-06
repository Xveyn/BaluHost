import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import FirmwareFanNotice from '../../../components/fan-control/FirmwareFanNotice';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
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
