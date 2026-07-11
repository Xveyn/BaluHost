import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDashboardStats, type UseDashboardStatsInput } from '../../hooks/useDashboardStats';
import type { SystemInfoResponse, TelemetryHistory } from '../../api/system';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const emptyHistory: TelemetryHistory = { cpu: [], memory: [], network: [] };

function sysInfo(overrides: Partial<SystemInfoResponse> = {}): SystemInfoResponse {
  return {
    cpu: { usage: 42, cores: 8, frequency_mhz: 3600, model: 'AMD Ryzen 5 5600GT', temperature_celsius: 55 },
    memory: { total: 16000, used: 8000, free: 8000, speed_mts: 3200, type: 'DDR4' },
    disk: {} as SystemInfoResponse['disk'],
    uptime: 100,
    system_uptime: 200,
    dev_mode: true,
    ...overrides,
  };
}

function baseInput(overrides: Partial<UseDashboardStatsInput> = {}): UseDashboardStatsInput {
  return { systemInfo: sysInfo(), storageInfo: { total: 1000, used: 400 }, smartData: null, history: emptyHistory, ...overrides };
}

describe('useDashboardStats', () => {
  it('derives systemStats with cpu clamp and storage percent', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.systemStats).toEqual({ cpuUsage: 42, cpuCores: 8, memoryUsed: 8000, memoryTotal: 16000, uptime: 100, systemUptime: 200 });
    expect(result.current.storageStats).toEqual({ used: 400, total: 1000, available: 600, percent: 40 });
    expect(result.current.memoryPercent).toBe(50);
  });

  it('clamps cpu usage over 100', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput({ systemInfo: sysInfo({ cpu: { usage: 150, cores: 4 } }) })));
    expect(result.current.systemStats.cpuUsage).toBe(100);
  });

  it('falls back to summed SMART capacity when no storageInfo', () => {
    const smartData = { checked_at: 'x', devices: [
      { name: 'a', model: 'm', serial: 's1', temperature: null, status: 'PASSED', capacity_bytes: 2000, used_bytes: 500, used_percent: null, mount_point: null, raid_member_of: null, last_self_test: null, attributes: [] },
    ] };
    const { result } = renderHook(() => useDashboardStats(baseInput({ storageInfo: null, smartData })));
    expect(result.current.storageStats.total).toBe(2000);
    expect(result.current.storageStats.used).toBe(500);
  });

  it('formats memoryDelta as Live when history < 2 points', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.memoryDelta).toEqual({ label: 'Live', tone: 'live' });
    expect(result.current.storageDelta).toEqual({ label: 'Live', tone: 'live' });
  });

  it('builds cpuStatBase with amd vendor and model meta', () => {
    const { result } = renderHook(() => useDashboardStats(baseInput()));
    expect(result.current.cpuStatBase.vendor).toBe('amd');
    expect(result.current.cpuStatBase.meta).toBe('AMD Ryzen 5 5600GT');
    expect(result.current.memorySpeedType).toBe('DDR4 @ 3200 MT/s');
  });
});
