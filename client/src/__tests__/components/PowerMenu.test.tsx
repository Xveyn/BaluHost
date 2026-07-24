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
  enableDesktop: vi.fn(),
}));

vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginMenuItems: [] }),
}));

import PowerMenu from '../../components/PowerMenu';
import { getSleepStatus } from '../../api/sleep';
import { getDesktopStatus, disableDesktop, enableDesktop } from '../../api/desktop';
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
    await waitFor(() => {
      expect(getDesktopStatus).toHaveBeenCalled();
      expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
    });
  });

  it('hides "Disable desktop" when the status lookup fails', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no desktop'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => {
      expect(getDesktopStatus).toHaveBeenCalled();
      expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
    });
  });

  it('clicking it calls disableDesktop and shows a success toast', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    (disableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, message: 'ok' });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const item = await screen.findByRole('button', { name: /Disable desktop/i });
    fireEvent.click(item);
    await waitFor(() => expect(disableDesktop).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('shows an error toast when disableDesktop returns success=false', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    (disableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false, message: 'DPMS unavailable',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByRole('button', { name: /Disable desktop/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('DPMS unavailable'));
  });

  it('does not show "Disable desktop" for non-admins', async () => {
    // No getDesktopStatus mock needed: the effect is gated on isAdmin,
    // so a non-admin never triggers the lookup.
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
    expect(getDesktopStatus).not.toHaveBeenCalled();
  });
});

describe('PowerMenu — enable desktop quick action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('shows "Enable desktop" when displays are stopped', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Enable desktop')).toBeInTheDocument();
  });

  it('hides "Enable desktop" when displays are running', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => {
      expect(getDesktopStatus).toHaveBeenCalled();
      expect(screen.queryByText('Enable desktop')).not.toBeInTheDocument();
    });
  });

  it('hides "Enable desktop" when the status lookup fails', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no desktop'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => {
      expect(getDesktopStatus).toHaveBeenCalled();
      expect(screen.queryByText('Enable desktop')).not.toBeInTheDocument();
    });
  });

  it('clicking it calls enableDesktop and shows a success toast', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, message: 'ok' });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const item = await screen.findByRole('button', { name: /Enable desktop/i });
    fireEvent.click(item);
    await waitFor(() => expect(enableDesktop).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('shows an error toast when enableDesktop returns success=false', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false, message: 'display manager offline',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByRole('button', { name: /Enable desktop/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('display manager offline'));
  });

  it('does not show "Enable desktop" for non-admins', async () => {
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    await act(async () => {});
    expect(screen.queryByText('Enable desktop')).not.toBeInTheDocument();
    expect(getDesktopStatus).not.toHaveBeenCalled();
  });
});

describe('PowerMenu session unlock hint', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('shows an extra hint when the session could not be unlocked', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped',
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      message: 'ok',
      session_unlocked: false,
      unlock_message: 'not permitted from this network',
    });

    render(<PowerMenu {...baseProps} />);
    openMenu();
    const button = await screen.findByText('Enable desktop');
    fireEvent.click(button);

    await waitFor(() => expect(enableDesktop).toHaveBeenCalledTimes(1));
    // The raw English debug string must never reach the user (#406).
    await waitFor(() =>
      expect(
        screen.queryByText(/not permitted from this network/i),
      ).not.toBeInTheDocument(),
    );
  });

  it('shows no hint when the session was unlocked', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped',
    });
    (enableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      message: 'ok',
      session_unlocked: true,
      unlock_message: 'session 2 unlocked',
    });

    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Enable desktop'));

    await waitFor(() => expect(enableDesktop).toHaveBeenCalledTimes(1));
  });
});
