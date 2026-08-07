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
}));

import toast from 'react-hot-toast';

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
