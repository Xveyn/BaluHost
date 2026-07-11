import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDashboardAlerts } from '../../hooks/useDashboardAlerts';
import type { SmartDevice, SmartStatusResponse } from '../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

function dev(status: string): SmartDevice {
  return { name: 'a', model: 'm', serial: 's-' + status, temperature: null, status, capacity_bytes: 1, used_bytes: 0, used_percent: 0, mount_point: null, raid_member_of: null, last_self_test: null, attributes: [] };
}
function smart(...statuses: string[]): SmartStatusResponse { return { checked_at: 'x', devices: statuses.map(dev) }; }

const noOther = { raidData: null, allSchedulers: [], services: [], isAdmin: false };

describe('useDashboardAlerts', () => {
  it('emits a critical alert for FAILED SMART devices', () => {
    const { result } = renderHook(() => useDashboardAlerts({ smartData: smart('FAILED', 'PASSED'), ...noOther }));
    const a = result.current.find(x => x.id === 'smart-failure');
    expect(a?.type).toBe('critical');
  });

  it('emits a warning alert for UNKNOWN SMART devices', () => {
    const { result } = renderHook(() => useDashboardAlerts({ smartData: smart('UNKNOWN'), ...noOther }));
    expect(result.current.find(x => x.id === 'smart-unknown')?.type).toBe('warning');
  });

  it('suppresses scheduler/service alerts for non-admins', () => {
    const schedulers = [{ last_status: 'failed' }] as never;
    const services = [{ state: 'error' }] as never;
    const { result } = renderHook(() => useDashboardAlerts({ smartData: null, raidData: null, allSchedulers: schedulers, services, isAdmin: false }));
    expect(result.current.some(x => x.id === 'scheduler-failed' || x.id === 'service-error')).toBe(false);
  });

  it('emits scheduler + service alerts for admins', () => {
    const schedulers = [{ last_status: 'failed' }] as never;
    const services = [{ state: 'error' }] as never;
    const { result } = renderHook(() => useDashboardAlerts({ smartData: null, raidData: null, allSchedulers: schedulers, services, isAdmin: true }));
    expect(result.current.some(x => x.id === 'scheduler-failed')).toBe(true);
    expect(result.current.some(x => x.id === 'service-error')).toBe(true);
  });
});
