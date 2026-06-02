import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Deterministic translations: return the inline default (2nd arg), else the key.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, def?: string) => def ?? _key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../api/sleep', () => ({
  getSleepStatus: vi.fn(),
  enterSoftSleep: vi.fn(),
  enterSuspend: vi.fn(),
}));

vi.mock('../../api/desktop', () => ({
  getDesktopStatus: vi.fn(),
  disableDesktop: vi.fn(),
}));

import PowerMenu from '../../components/PowerMenu';
import { getSleepStatus } from '../../api/sleep';
import { getDesktopStatus, disableDesktop } from '../../api/desktop';
import toast from 'react-hot-toast';

const baseProps = {
  isAdmin: true,
  onShutdown: vi.fn().mockResolvedValue(undefined),
  onRestart: vi.fn().mockResolvedValue(undefined),
  onLogout: vi.fn(),
};

function openMenu() {
  fireEvent.click(screen.getByTitle('Power'));
}

describe('PowerMenu — disable desktop quick action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('shows "Disable desktop" when displays are running', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Disable desktop')).toBeInTheDocument();
  });

  it('hides "Disable desktop" when displays are stopped', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => expect(getDesktopStatus).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
  });

  it('hides "Disable desktop" when the status lookup fails', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no desktop'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => expect(getDesktopStatus).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
  });

  it('clicking it calls disableDesktop and shows a success toast', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    (disableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, message: 'ok' });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const item = await screen.findByText('Disable desktop');
    fireEvent.click(item);
    await waitFor(() => expect(disableDesktop).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('does not show "Disable desktop" for non-admins', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
    expect(getDesktopStatus).not.toHaveBeenCalled();
  });
});
