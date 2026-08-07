import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithQueryClient } from '../helpers/queryClient';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../hooks/useFanControl', () => ({ useFanControl: vi.fn() }));

// The page itself fetches profiles/sensors on mount (fire-and-forget, fails
// silently by design) — stub those three so the test doesn't depend on a
// real backend being reachable. Everything else in the module (FanMode, the
// FanInfo type, etc.) stays real.
vi.mock('../../api/fan-control', async () => {
  const actual = await vi.importActual<typeof import('../../api/fan-control')>('../../api/fan-control');
  return {
    ...actual,
    listProfiles: vi.fn().mockResolvedValue({ profiles: [], total_count: 0 }),
    listTempSensors: vi.fn().mockResolvedValue({ sensors: [], total_count: 0 }),
    listComposites: vi.fn().mockResolvedValue({ composites: [], total_count: 0 }),
  };
});

// FanSchedulePanel is a real, fairly heavy component with its own API calls
// on mount (schedule entries). Stub it down to a prop probe — this test is
// only about which `isReadOnly` value FanControl.tsx computes and passes in,
// not about FanSchedulePanel's own behavior (that's covered elsewhere).
vi.mock('../../components/fan-control', async () => {
  const actual = await vi.importActual<typeof import('../../components/fan-control')>('../../components/fan-control');
  return {
    ...actual,
    FanSchedulePanel: (props: { isReadOnly: boolean }) => (
      <div data-testid="schedule-panel-readonly">{String(props.isReadOnly)}</div>
    ),
  };
});

import { useFanControl } from '../../hooks/useFanControl';
import { FanMode } from '../../api/fan-control';
import type { FanInfo } from '../../api/fan-control';
import FanControl from '../../pages/FanControl';

function fan(overrides: Partial<FanInfo> = {}): FanInfo {
  return {
    fan_id: 'hwmon2_pwm1',
    name: 'Fan',
    rpm: 1200,
    pwm_percent: 40,
    temperature_celsius: 55,
    mode: FanMode.SCHEDULED,
    is_active: true,
    min_pwm_percent: 30,
    max_pwm_percent: 100,
    emergency_temp_celsius: 95,
    temp_sensor_id: null,
    curve_points: [],
    hysteresis_celsius: 3,
    pwm_control: 'supported',
    ...overrides,
  };
}

function mockStatus(fans: FanInfo[]) {
  (useFanControl as any).mockReturnValue({
    status: {
      fans,
      is_dev_mode: true,
      is_using_linux_backend: false,
      permission_status: 'ok',
      backend_available: true,
    },
    permissionStatus: { has_write_permission: true, status: 'ok', message: '', suggestions: [] },
    loading: false,
    refetch: vi.fn(),
    isReadOnly: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FanControl Seite: Zeitplan-Sperre folgt dem ausgewaehlten Luefter, nicht global', () => {
  it('laesst den Zeitplan eines normalen Luefters editierbar', async () => {
    mockStatus([fan({ fan_id: 'case_pwm1', name: 'Case Fan', pwm_control: 'supported' })]);
    renderWithQueryClient(<FanControl />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-panel-readonly').textContent).toBe('false');
    });
  });

  it('sperrt den Zeitplan eines firmware-verwalteten Luefters, obwohl die Seite isReadOnly=false meldet', async () => {
    mockStatus([fan({ fan_id: 'gpu_pwm1', name: 'GPU Fan', pwm_control: 'firmware_managed' })]);
    renderWithQueryClient(<FanControl />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-panel-readonly').textContent).toBe('true');
    });
  });

  it('sperrt nur den ausgewaehlten firmware-verwalteten Luefter, nicht die ganze Box (per-Fan statt global)', async () => {
    mockStatus([
      fan({ fan_id: 'case_pwm1', name: 'Case Fan', mode: FanMode.SCHEDULED, pwm_control: 'supported' }),
      fan({ fan_id: 'gpu_pwm1', name: 'GPU Fan', mode: FanMode.SCHEDULED, pwm_control: 'firmware_managed' }),
    ]);
    renderWithQueryClient(<FanControl />);

    // Case Fan is auto-selected (first in the list) -> schedule stays editable.
    await waitFor(() => {
      expect(screen.getByTestId('schedule-panel-readonly').textContent).toBe('false');
    });

    // Selecting the GPU fan instead locks the panel for that fan specifically.
    fireEvent.click(screen.getByText('GPU Fan'));
    await waitFor(() => {
      expect(screen.getByTestId('schedule-panel-readonly').textContent).toBe('true');
    });
  });
});

describe('FanControl Seite: Profile-Panel fuer firmware-verwaltete Luefter gesperrt', () => {
  it('zeigt den Profile Manager fuer einen normalen Luefter', async () => {
    mockStatus([fan({ fan_id: 'case_pwm1', name: 'Case Fan', pwm_control: 'supported' })]);
    renderWithQueryClient(<FanControl />);
    await waitFor(() => {
      expect(screen.getByText('system:fanControl.profiles.title')).toBeTruthy();
    });
  });

  it('versteckt den Profile Manager fuer einen firmware-verwalteten Luefter, obwohl isReadOnly=false', async () => {
    mockStatus([fan({ fan_id: 'gpu_pwm1', name: 'GPU Fan', pwm_control: 'firmware_managed' })]);
    renderWithQueryClient(<FanControl />);
    // Warten, bis die Seite fertig gerendert hat (Fan-Karte sichtbar), dann
    // pruefen, dass der Profile Manager (der nachweislich nie an diesen
    // Luefter schreiben kann) nicht erscheint.
    await waitFor(() => {
      expect(screen.getByText('GPU Fan')).toBeTruthy();
    });
    expect(screen.queryByText('system:fanControl.profiles.title')).toBeNull();
  });
});
