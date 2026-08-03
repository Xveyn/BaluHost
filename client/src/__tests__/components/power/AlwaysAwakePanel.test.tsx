import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AlwaysAwakePanel } from '../../../components/power/AlwaysAwakePanel';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
  getCoreUptimeOccurrences,
} from '../../../api/sleep';

vi.mock('../../../api/sleep', () => ({
  getSleepConfig: vi.fn(),
  getSleepStatus: vi.fn(),
  updateSleepConfig: vi.fn(),
  getCoreUptimeOccurrences: vi.fn(),
}));

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}));

const mockedConfig = vi.mocked(getSleepConfig);
const mockedStatus = vi.mocked(getSleepStatus);
const mockedUpdate = vi.mocked(updateSleepConfig);
const mockedOccurrences = vi.mocked(getCoreUptimeOccurrences);

/** Fenster, das in 4 Stunden beginnt und 6 Stunden dauert. */
function windowInHours(startInHours: number, durationHours: number) {
  const start = new Date(Date.now() + startInHours * 3600 * 1000);
  const end = new Date(start.getTime() + durationHours * 3600 * 1000);
  return {
    window_id: 1,
    label: 'Abend',
    start: start.toISOString(),
    end: end.toISOString(),
  };
}

function baseConfig(overrides: Record<string, unknown> = {}) {
  return {
    always_awake_enabled: false,
    always_awake_until: null,
    schedule_enabled: false,
    core_uptime_enabled: true,
    ...overrides,
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedStatus.mockResolvedValue({ always_awake: { expires_in_seconds: null } } as never);
  mockedUpdate.mockResolvedValue({} as never);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AlwaysAwakePanel — Kernbetriebszeit-Kuerzung', () => {
  // i18n ist in Component-Tests nicht initialisiert: t() liefert den rohen Key.

  it('sends the clamped value when the chosen expiry falls into a window', async () => {
    const occurrence = windowInHours(4, 6); // beginnt in 4h, laeuft 6h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    // "8h" landet 8h in der Zukunft — also innerhalb des Fensters (4h..10h).
    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    expect(mockedUpdate).toHaveBeenCalledWith({
      always_awake_enabled: true,
      always_awake_until: occurrence.start,
    });
  });

  it('sends the raw value when the chosen expiry clears the window end', async () => {
    const occurrence = windowInHours(1, 2); // 1h..3h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    const sent = mockedUpdate.mock.calls[0][0] as { always_awake_until: string };
    expect(sent.always_awake_until).not.toBe(occurrence.start);
  });

  it('shows the clamp hint while the affected preset is focused', async () => {
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([windowInHours(4, 6)] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(screen.queryByText('sleep.alwaysAwake.clampPreview')).not.toBeInTheDocument();
    await user.hover(button);
    expect(await screen.findByText('sleep.alwaysAwake.clampPreview')).toBeInTheDocument();
  });

  it('explains an already-clamped active override after reload', async () => {
    const occurrence = windowInHours(4, 6);
    mockedConfig.mockResolvedValue(
      baseConfig({ always_awake_enabled: true, always_awake_until: occurrence.start }),
    );
    mockedStatus.mockResolvedValue({
      always_awake: { expires_in_seconds: 4 * 3600 },
    } as never);
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    render(<AlwaysAwakePanel />);

    expect(await screen.findByText('sleep.alwaysAwake.clampActive')).toBeInTheDocument();
  });

  it('reports a currently running window instead of a clamp hint', async () => {
    const start = new Date(Date.now() - 3600 * 1000);
    const end = new Date(Date.now() + 3 * 3600 * 1000);
    mockedConfig.mockResolvedValue(
      baseConfig({ always_awake_enabled: true, always_awake_until: end.toISOString() }),
    );
    mockedStatus.mockResolvedValue({
      always_awake: { expires_in_seconds: 3 * 3600 },
    } as never);
    mockedOccurrences.mockResolvedValue([
      { window_id: 1, label: null, start: start.toISOString(), end: end.toISOString() },
    ] as never);

    render(<AlwaysAwakePanel />);

    expect(await screen.findByText('sleep.alwaysAwake.coreUptimeRunning')).toBeInTheDocument();
    expect(screen.queryByText('sleep.alwaysAwake.clampActive')).not.toBeInTheDocument();
  });

  it('does not request occurrences when core uptime is disabled', async () => {
    mockedConfig.mockResolvedValue(baseConfig({ core_uptime_enabled: false }));
    mockedOccurrences.mockResolvedValue([] as never);

    render(<AlwaysAwakePanel />);

    await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(mockedOccurrences).not.toHaveBeenCalled();
  });
});
