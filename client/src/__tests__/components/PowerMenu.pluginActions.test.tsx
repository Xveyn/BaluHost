import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, def?: string) => def ?? _key }),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/sleep', () => ({
  getSleepStatus: vi.fn(), enterSoftSleep: vi.fn(), enterSuspend: vi.fn(),
}));
vi.mock('../../api/desktop', () => ({
  getDesktopStatus: vi.fn(), disableDesktop: vi.fn(), enableDesktop: vi.fn(),
}));
vi.mock('../../api/plugins', () => ({ runPluginMenuAction: vi.fn() }));

// vi.mock factories are hoisted above this file's const declarations — a plain
// top-level array would hit the temporal dead zone. vi.hoisted lifts the state
// alongside the mock.
const menuItems = vi.hoisted(() => [] as unknown[]);
vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginMenuItems: menuItems }),
}));

import PowerMenu from '../../components/PowerMenu';
import { getSleepStatus } from '../../api/sleep';
import { getDesktopStatus } from '../../api/desktop';
import { runPluginMenuAction } from '../../api/plugins';
import toast from 'react-hot-toast';

const baseProps = {
  isAdmin: true,
  onShutdown: vi.fn().mockResolvedValue(undefined),
  onRestart: vi.fn().mockResolvedValue(undefined),
  onLogout: vi.fn(),
};

const gamingItem = {
  id: 'gaming_mode', icon: 'Gamepad2', tone: 'info', order: 10,
  label_key: 'menu_gaming_mode', label_text: 'Gaming Mode',
  description_key: 'menu_gaming_mode_desc', description_text: 'Displays on + Big Picture',
  _pluginName: 'steam_gaming',
  _translations: { en: { menu_gaming_mode: 'Gaming Mode' } },
};

function setItems(items: unknown[]) {
  menuItems.length = 0;
  menuItems.push(...items);
}

const openMenu = () => fireEvent.click(screen.getByTitle('Power'));

describe('PowerMenu — plugin menu actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (getDesktopStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    setItems([gamingItem]);
  });

  it('renders a plugin action with its resolved label', async () => {
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Gaming Mode')).toBeInTheDocument();
  });

  it('posts to the right plugin and action on click', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true, message_key: null, message_text: 'Gaming mode started',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() =>
      expect(runPluginMenuAction).toHaveBeenCalledWith('steam_gaming', 'gaming_mode'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Gaming mode started'));
  });

  it('shows an error toast when the action reports ok:false', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false, message_key: null, message_text: 'Steam did not start',
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Steam did not start'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows an error toast when the request itself fails', async () => {
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    fireEvent.click(await screen.findByText('Gaming Mode'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it('renders an item whose icon is unknown instead of crashing', async () => {
    setItems([{ ...gamingItem, icon: 'NotARealIcon' }]);
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Gaming Mode')).toBeInTheDocument();
  });

  it('renders no plugin actions for a non-admin', async () => {
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    expect(screen.queryByText('Gaming Mode')).not.toBeInTheDocument();
  });

  it('locks the plugin actions while one is running', async () => {
    let resolveAction!: (value: unknown) => void;
    (runPluginMenuAction as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((resolve) => { resolveAction = resolve; }),
    );
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const button = (await screen.findByText('Gaming Mode')).closest('button')!;
    fireEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());

    resolveAction({ ok: true, message_key: null, message_text: 'done' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('done'));
  });
});
