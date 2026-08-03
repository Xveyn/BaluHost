import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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

  it('sends the raw value to the backend but displays the clamped value optimistically', async () => {
    // The backend re-applies clamp_to_core_uptime_start on whatever it receives.
    // Sending the already-clamped value would double-clamp on staggered,
    // overlapping windows (regression: see coreUptimeClamp.test.ts) — the UI
    // must send the RAW pick and keep the clamp purely for its own optimistic
    // display, matching what the backend's single clamp of the raw value
    // produces.
    const occurrence = windowInHours(4, 6); // beginnt in 4h, laeuft 6h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    const before = Date.now();
    render(<AlwaysAwakePanel />);

    // "8h" landet 8h in der Zukunft — also innerhalb des Fensters (4h..10h).
    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    const after = Date.now();

    // Sent value: the RAW "now + 8h" pick, unclamped. Bounded by the actual
    // wall-clock span of this test, not a hardcoded offset — a wrongly-sent
    // clamped value (occurrence.start, ~4h out) would fail this assertion.
    const sent = mockedUpdate.mock.calls[0][0] as { always_awake_until: string };
    const sentMs = new Date(sent.always_awake_until).getTime();
    expect(sentMs).toBeGreaterThanOrEqual(before + 8 * 3600 * 1000 - 2000);
    expect(sentMs).toBeLessThanOrEqual(after + 8 * 3600 * 1000 + 2000);

    // Displayed value: the clamped occurrence start — what the backend's own
    // clamp of that raw value will also settle on.
    expect(await screen.findByText('sleep.alwaysAwake.clampActive')).toBeInTheDocument();
  });

  it('sends the raw value when the chosen expiry clears the window end', async () => {
    const occurrence = windowInHours(1, 2); // 1h..3h
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([occurrence] as never);

    const user = userEvent.setup();
    const before = Date.now();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    await user.click(button);

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
    const after = Date.now();
    const sent = mockedUpdate.mock.calls[0][0] as { always_awake_until: string };
    const sentMs = new Date(sent.always_awake_until).getTime();
    // Unclamped: the preset is "now + 8h" computed at click time. Bound it by
    // the actual wall-clock span of this test (before/after), with a small
    // tolerance for clock-read precision — not a hardcoded date or offset.
    // The 1h..3h window is far outside this range, so a wrongly-clamped
    // value (occurrence.start, ~1h out) would fail this assertion.
    expect(sentMs).toBeGreaterThanOrEqual(before + 8 * 3600 * 1000 - 2000);
    expect(sentMs).toBeLessThanOrEqual(after + 8 * 3600 * 1000 + 2000);
  });

  it('shows the clamp hint on hover', async () => {
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([windowInHours(4, 6)] as never);

    const user = userEvent.setup();
    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(screen.queryByText('sleep.alwaysAwake.clampPreview')).not.toBeInTheDocument();
    await user.hover(button);
    expect(await screen.findByText('sleep.alwaysAwake.clampPreview')).toBeInTheDocument();
  });

  it('shows the clamp hint on keyboard focus', async () => {
    mockedConfig.mockResolvedValue(baseConfig());
    mockedOccurrences.mockResolvedValue([windowInHours(4, 6)] as never);

    render(<AlwaysAwakePanel />);

    const button = await screen.findByText('sleep.alwaysAwake.preset8h');
    expect(screen.queryByText('sleep.alwaysAwake.clampPreview')).not.toBeInTheDocument();
    fireEvent.focus(button);
    expect(await screen.findByText('sleep.alwaysAwake.clampPreview')).toBeInTheDocument();
    fireEvent.blur(button);
    await waitFor(() =>
      expect(screen.queryByText('sleep.alwaysAwake.clampPreview')).not.toBeInTheDocument(),
    );
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

  it('reports a currently running window instead of a clamp-active hint, even when until equals the window start', async () => {
    const start = new Date(Date.now() - 3600 * 1000);
    const end = new Date(Date.now() + 3 * 3600 * 1000);
    // `always_awake_until` deliberately equals the running occurrence's
    // `start` — this is exactly the shape `activeClamp` matches on
    // (`until === occurrence.start`). Without the `!runningOccurrence`
    // guard in AlwaysAwakePanel, this would also render clampActive; this
    // test proves the guard actually suppresses it in favour of
    // coreUptimeRunning.
    mockedConfig.mockResolvedValue(
      baseConfig({ always_awake_enabled: true, always_awake_until: start.toISOString() }),
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
