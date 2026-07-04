import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useLiveActivities } from '../../hooks/useLiveActivities';
import * as fanApi from '../../api/fan-control';
import * as powerApi from '../../api/power-management';
import type { FanStatusResponse } from '../../api/fan-control';
import type { PowerStatusResponse } from '../../api/power-management';
import type { SchedulerStatus } from '../../api/schedulers';
import type { RaidStatusResponse } from '../../api/raid';

vi.mock('../../api/fan-control');
vi.mock('../../api/power-management');
const fan = vi.mocked(fanApi);
const power = vi.mocked(powerApi);

const runningScheduler = {
  name: 'raid_scrub',
  display_name: 'RAID Scrub',
  is_running: true,
} as unknown as SchedulerStatus;

const raidData = {
  arrays: [{ name: 'md0', status: 'rebuilding', resync_progress: 42 }],
} as unknown as RaidStatusResponse;

const fanStatus = {
  fans: [
    { fan_id: 'cpu', mode: 'scheduled', active_schedule: { name: 'Night', end_time: '06:00' } },
  ],
} as unknown as FanStatusResponse;

const powerStatus = {
  active_demands: [{ level: 'surge', source: 'benchmark' }],
} as unknown as PowerStatusResponse;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useLiveActivities', () => {
  it('derives scheduler/raid activities without polling fans/power for non-admins', async () => {
    const { result } = renderHook(
      () => useLiveActivities({ raidData, schedulers: [runningScheduler], isAdmin: false }),
      { wrapper: createQueryWrapper() },
    );

    // Non-admin: fan/power queries are disabled.
    expect(fan.getFanStatus).not.toHaveBeenCalled();
    expect(power.getPowerStatus).not.toHaveBeenCalled();

    const ids = result.current.activities.map((a) => a.id);
    expect(ids).toContain('scheduler-raid_scrub');
    expect(ids).toContain('raid-md0');
  });

  it('adds fan + power activities once the admin queries resolve', async () => {
    fan.getFanStatus.mockResolvedValue(fanStatus);
    power.getPowerStatus.mockResolvedValue(powerStatus);

    const { result } = renderHook(
      () => useLiveActivities({ raidData: null, schedulers: [], isAdmin: true }),
      { wrapper: createQueryWrapper() },
    );

    await waitFor(() => {
      const ids = result.current.activities.map((a) => a.id);
      expect(ids).toContain('fan-cpu');
      expect(ids).toContain('power-elevated');
    });
    expect(fan.getFanStatus).toHaveBeenCalled();
    expect(power.getPowerStatus).toHaveBeenCalled();
  });
});
