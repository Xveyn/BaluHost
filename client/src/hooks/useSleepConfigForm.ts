import { useState, useCallback } from 'react';
import type { SleepConfigResponse, SleepConfigUpdate, ScheduleMode, PresenceMode } from '../api/sleep';

export interface SleepConfigForm {
  autoIdleEnabled: boolean;
  idleTimeout: number;
  idleCpuThreshold: number;
  idleDiskIoThreshold: number;
  idleHttpThreshold: number;
  escalationEnabled: boolean;
  escalationMinutes: number;
  scheduleEnabled: boolean;
  scheduleSleepTime: string;
  scheduleWakeTime: string;
  scheduleMode: ScheduleMode;
  wolMac: string;
  wolBroadcast: string;
  pauseMonitoring: boolean;
  pauseDiskIo: boolean;
  reducedTelemetry: number;
  diskSpindown: boolean;
  presenceEnabled: boolean;
  presenceMode: PresenceMode;
  presenceTimeout: number;
}

const DEFAULT_FORM: SleepConfigForm = {
  autoIdleEnabled: false,
  idleTimeout: 15,
  idleCpuThreshold: 5.0,
  idleDiskIoThreshold: 0.5,
  idleHttpThreshold: 5.0,
  escalationEnabled: false,
  escalationMinutes: 60,
  scheduleEnabled: false,
  scheduleSleepTime: '23:00',
  scheduleWakeTime: '06:00',
  scheduleMode: 'soft',
  wolMac: '',
  wolBroadcast: '',
  pauseMonitoring: true,
  pauseDiskIo: true,
  reducedTelemetry: 30,
  diskSpindown: true,
  presenceEnabled: true,
  presenceMode: 'active',
  presenceTimeout: 3,
};

export interface UseSleepConfigFormResult {
  form: SleepConfigForm;
  update: (patch: Partial<SleepConfigForm>) => void;
  syncFromResponse: (c: SleepConfigResponse) => void;
  toPayload: () => SleepConfigUpdate;
}

export function useSleepConfigForm(): UseSleepConfigFormResult {
  const [form, setForm] = useState<SleepConfigForm>(DEFAULT_FORM);

  const update = useCallback((patch: Partial<SleepConfigForm>) => {
    setForm((f) => ({ ...f, ...patch }));
  }, []);

  const syncFromResponse = useCallback((c: SleepConfigResponse) => {
    setForm({
      autoIdleEnabled: c.auto_idle_enabled,
      idleTimeout: c.idle_timeout_minutes,
      idleCpuThreshold: c.idle_cpu_threshold,
      idleDiskIoThreshold: c.idle_disk_io_threshold,
      idleHttpThreshold: c.idle_http_threshold,
      escalationEnabled: c.auto_escalation_enabled,
      escalationMinutes: c.escalation_after_minutes,
      scheduleEnabled: c.schedule_enabled,
      scheduleSleepTime: c.schedule_sleep_time,
      scheduleWakeTime: c.schedule_wake_time,
      scheduleMode: c.schedule_mode,
      wolMac: c.wol_mac_address || '',
      wolBroadcast: c.wol_broadcast_address || '',
      pauseMonitoring: c.pause_monitoring,
      pauseDiskIo: c.pause_disk_io,
      reducedTelemetry: c.reduced_telemetry_interval,
      diskSpindown: c.disk_spindown_enabled,
      presenceEnabled: c.presence_enabled,
      presenceMode: c.presence_mode,
      presenceTimeout: c.presence_timeout_minutes,
    });
  }, []);

  const toPayload = useCallback((): SleepConfigUpdate => ({
    auto_idle_enabled: form.autoIdleEnabled,
    idle_timeout_minutes: form.idleTimeout,
    idle_cpu_threshold: form.idleCpuThreshold,
    idle_disk_io_threshold: form.idleDiskIoThreshold,
    idle_http_threshold: form.idleHttpThreshold,
    auto_escalation_enabled: form.escalationEnabled,
    escalation_after_minutes: form.escalationMinutes,
    schedule_enabled: form.scheduleEnabled,
    schedule_sleep_time: form.scheduleSleepTime,
    schedule_wake_time: form.scheduleWakeTime,
    schedule_mode: form.scheduleMode,
    wol_mac_address: form.wolMac || null,
    wol_broadcast_address: form.wolBroadcast || null,
    pause_monitoring: form.pauseMonitoring,
    pause_disk_io: form.pauseDiskIo,
    reduced_telemetry_interval: form.reducedTelemetry,
    disk_spindown_enabled: form.diskSpindown,
    presence_enabled: form.presenceEnabled,
    presence_mode: form.presenceMode,
    presence_timeout_minutes: form.presenceTimeout,
  }), [form]);

  return { form, update, syncFromResponse, toPayload };
}
