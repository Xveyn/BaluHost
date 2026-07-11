import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSleepConfigForm } from '../../hooks/useSleepConfigForm';
import type { SleepConfigResponse, SleepConfigUpdate } from '../../api/sleep';

const response: SleepConfigResponse = {
  auto_idle_enabled: true, idle_timeout_minutes: 30, idle_cpu_threshold: 7.5,
  idle_disk_io_threshold: 1.0, idle_http_threshold: 10,
  auto_escalation_enabled: true, escalation_after_minutes: 90,
  schedule_enabled: true, schedule_sleep_time: '22:30', schedule_wake_time: '07:15',
  schedule_mode: 'suspend',
  wol_mac_address: 'AA:BB:CC:DD:EE:FF', wol_broadcast_address: '10.0.0.255',
  pause_monitoring: false, pause_disk_io: false, reduced_telemetry_interval: 45,
  disk_spindown_enabled: false,
  core_uptime_enabled: false, core_uptime_suspend_on_exit: false,
  presence_enabled: false, presence_mode: 'session', presence_timeout_minutes: 5,
};

describe('useSleepConfigForm', () => {
  it('has sensible defaults before sync', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    expect(result.current.form.idleTimeout).toBe(15);
    expect(result.current.form.pauseMonitoring).toBe(true);
    expect(result.current.form.presenceMode).toBe('active');
  });

  it('round-trips response -> syncFromResponse -> toPayload', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.syncFromResponse(response));

    const expected: SleepConfigUpdate = {
      auto_idle_enabled: true, idle_timeout_minutes: 30, idle_cpu_threshold: 7.5,
      idle_disk_io_threshold: 1.0, idle_http_threshold: 10,
      auto_escalation_enabled: true, escalation_after_minutes: 90,
      schedule_enabled: true, schedule_sleep_time: '22:30', schedule_wake_time: '07:15',
      schedule_mode: 'suspend',
      wol_mac_address: 'AA:BB:CC:DD:EE:FF', wol_broadcast_address: '10.0.0.255',
      pause_monitoring: false, pause_disk_io: false, reduced_telemetry_interval: 45,
      disk_spindown_enabled: false,
      presence_enabled: false, presence_mode: 'session', presence_timeout_minutes: 5,
    };
    expect(result.current.toPayload()).toEqual(expected);
  });

  it('maps empty WoL strings to null in the payload', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.syncFromResponse({ ...response, wol_mac_address: null, wol_broadcast_address: null }));
    const payload = result.current.toPayload();
    expect(payload.wol_mac_address).toBeNull();
    expect(payload.wol_broadcast_address).toBeNull();
  });

  it('update patches one field without clobbering others', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.update({ idleTimeout: 99 }));
    expect(result.current.form.idleTimeout).toBe(99);
    expect(result.current.form.pauseMonitoring).toBe(true); // untouched default
  });
});
