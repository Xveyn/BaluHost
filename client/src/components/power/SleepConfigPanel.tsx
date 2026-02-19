/**
 * Sleep Config Panel - Configuration for sleep mode.
 *
 * Includes auto-idle detection settings, schedule, WoL,
 * service pausing options, and disk spindown.
 */

import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Settings, Clock, Wifi, Server, HardDrive, Timer, TrendingUp, ChevronDown, Terminal } from 'lucide-react';
import {
  getSleepConfig,
  updateSleepConfig,
  getSleepCapabilities,
  type SleepConfigResponse,
  type SleepCapabilities,
  type ScheduleMode,
} from '../../api/sleep';

export function SleepConfigPanel() {
  const [capabilities, setCapabilities] = useState<SleepCapabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  // Form state
  const [autoIdleEnabled, setAutoIdleEnabled] = useState(false);
  const [idleTimeout, setIdleTimeout] = useState(15);
  const [idleCpuThreshold, setIdleCpuThreshold] = useState(5.0);
  const [idleDiskIoThreshold, setIdleDiskIoThreshold] = useState(0.5);
  const [idleHttpThreshold, setIdleHttpThreshold] = useState(5.0);
  const [escalationEnabled, setEscalationEnabled] = useState(false);
  const [escalationMinutes, setEscalationMinutes] = useState(60);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleSleepTime, setScheduleSleepTime] = useState('23:00');
  const [scheduleWakeTime, setScheduleWakeTime] = useState('06:00');
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>('soft');
  const [wolMac, setWolMac] = useState('');
  const [wolBroadcast, setWolBroadcast] = useState('');
  const [pauseMonitoring, setPauseMonitoring] = useState(true);
  const [pauseDiskIo, setPauseDiskIo] = useState(true);
  const [reducedTelemetry, setReducedTelemetry] = useState(30);
  const [diskSpindown, setDiskSpindown] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [configData, caps] = await Promise.all([
        getSleepConfig(),
        getSleepCapabilities(),
      ]);
      setCapabilities(caps);
      syncFormState(configData);
    } catch {
      toast.error('Failed to load sleep config');
    } finally {
      setLoading(false);
    }
  };

  const syncFormState = (c: SleepConfigResponse) => {
    setAutoIdleEnabled(c.auto_idle_enabled);
    setIdleTimeout(c.idle_timeout_minutes);
    setIdleCpuThreshold(c.idle_cpu_threshold);
    setIdleDiskIoThreshold(c.idle_disk_io_threshold);
    setIdleHttpThreshold(c.idle_http_threshold);
    setEscalationEnabled(c.auto_escalation_enabled);
    setEscalationMinutes(c.escalation_after_minutes);
    setScheduleEnabled(c.schedule_enabled);
    setScheduleSleepTime(c.schedule_sleep_time);
    setScheduleWakeTime(c.schedule_wake_time);
    setScheduleMode(c.schedule_mode);
    setWolMac(c.wol_mac_address || '');
    setWolBroadcast(c.wol_broadcast_address || '');
    setPauseMonitoring(c.pause_monitoring);
    setPauseDiskIo(c.pause_disk_io);
    setReducedTelemetry(c.reduced_telemetry_interval);
    setDiskSpindown(c.disk_spindown_enabled);
  };

  const handleSave = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await updateSleepConfig({
        auto_idle_enabled: autoIdleEnabled,
        idle_timeout_minutes: idleTimeout,
        idle_cpu_threshold: idleCpuThreshold,
        idle_disk_io_threshold: idleDiskIoThreshold,
        idle_http_threshold: idleHttpThreshold,
        auto_escalation_enabled: escalationEnabled,
        escalation_after_minutes: escalationMinutes,
        schedule_enabled: scheduleEnabled,
        schedule_sleep_time: scheduleSleepTime,
        schedule_wake_time: scheduleWakeTime,
        schedule_mode: scheduleMode,
        wol_mac_address: wolMac || null,
        wol_broadcast_address: wolBroadcast || null,
        pause_monitoring: pauseMonitoring,
        pause_disk_io: pauseDiskIo,
        reduced_telemetry_interval: reducedTelemetry,
        disk_spindown_enabled: diskSpindown,
      });
      toast.success('Sleep configuration saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-40 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Capabilities Info */}
      {capabilities && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
            <Settings className="h-4 w-4 text-slate-400" />
            System Capabilities
          </h4>
          <div className="flex flex-wrap gap-2">
            <CapBadge label="hdparm" ok={capabilities.hdparm_available} />
            <CapBadge label="rtcwake" ok={capabilities.rtcwake_available} />
            <CapBadge label="systemctl" ok={capabilities.systemctl_available} />
            <CapBadge label="Suspend" ok={capabilities.can_suspend} />
            <CapBadge label={`WoL (${capabilities.wol_interfaces.length} ifaces)`} ok={capabilities.wol_interfaces.length > 0} />
            <CapBadge label={`${capabilities.data_disk_devices.length} data disks`} ok={capabilities.data_disk_devices.length > 0} />
          </div>
          <CapabilityHelp capabilities={capabilities} open={helpOpen} onToggle={() => setHelpOpen(!helpOpen)} />
        </div>
      )}

      {/* Auto-Idle Detection */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <Timer className="h-4 w-4 text-blue-400" />
            Auto-Idle Detection
          </h4>
          <Toggle checked={autoIdleEnabled} onChange={setAutoIdleEnabled} />
        </div>

        {autoIdleEnabled && (
          <div className="space-y-3 pl-1">
            <NumberInput label="Idle timeout (min)" value={idleTimeout} onChange={setIdleTimeout} min={1} max={1440} />
            <NumberInput label="CPU threshold (%)" value={idleCpuThreshold} onChange={setIdleCpuThreshold} min={0} max={100} step={0.5} />
            <NumberInput label="Disk I/O threshold (MB/s)" value={idleDiskIoThreshold} onChange={setIdleDiskIoThreshold} min={0} step={0.1} />
            <NumberInput label="HTTP req/min threshold" value={idleHttpThreshold} onChange={setIdleHttpThreshold} min={0} step={1} />
          </div>
        )}
      </div>

      {/* Auto-Escalation */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-purple-400" />
            Auto-Escalation (Soft Sleep → Suspend)
          </h4>
          <Toggle checked={escalationEnabled} onChange={setEscalationEnabled} />
        </div>

        {escalationEnabled && (
          <div className="pl-1">
            <NumberInput label="Escalate after (min)" value={escalationMinutes} onChange={setEscalationMinutes} min={1} max={1440} />
          </div>
        )}
      </div>

      {/* Schedule */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-400" />
            Sleep Schedule
          </h4>
          <Toggle checked={scheduleEnabled} onChange={setScheduleEnabled} />
        </div>

        {scheduleEnabled && (
          <div className="space-y-3 pl-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Sleep at</label>
                <input
                  type="time"
                  value={scheduleSleepTime}
                  onChange={(e) => setScheduleSleepTime(e.target.value)}
                  className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Wake at</label>
                <input
                  type="time"
                  value={scheduleWakeTime}
                  onChange={(e) => setScheduleWakeTime(e.target.value)}
                  className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Schedule Mode</label>
              <select
                value={scheduleMode}
                onChange={(e) => setScheduleMode(e.target.value as ScheduleMode)}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              >
                <option value="soft">Soft Sleep</option>
                <option value="suspend">True Suspend</option>
              </select>
            </div>
          </div>
        )}
      </div>

      {/* WoL Configuration */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Wifi className="h-4 w-4 text-amber-400" />
          Wake-on-LAN
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">MAC Address</label>
            <input
              type="text"
              value={wolMac}
              onChange={(e) => setWolMac(e.target.value)}
              placeholder="AA:BB:CC:DD:EE:FF"
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Broadcast Address</label>
            <input
              type="text"
              value={wolBroadcast}
              onChange={(e) => setWolBroadcast(e.target.value)}
              placeholder="255.255.255.255"
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Service & Disk Options */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Server className="h-4 w-4 text-teal-400" />
          Sleep Behavior
        </h4>
        <div className="space-y-3">
          <ToggleRow label="Pause monitoring" checked={pauseMonitoring} onChange={setPauseMonitoring} />
          <ToggleRow label="Pause disk I/O monitor" checked={pauseDiskIo} onChange={setPauseDiskIo} />
          <ToggleRow
            label="Spin down data disks"
            checked={diskSpindown}
            onChange={setDiskSpindown}
            icon={<HardDrive className="h-3.5 w-3.5 text-slate-400" />}
          />
          <NumberInput
            label="Reduced telemetry interval (s)"
            value={reducedTelemetry}
            onChange={setReducedTelemetry}
            min={5}
            max={300}
          />
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={busy}
          className="rounded-lg bg-teal-500/20 px-6 py-2.5 text-sm font-medium text-teal-300 hover:bg-teal-500/30 transition-colors disabled:opacity-50"
        >
          {busy ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}

// ---- Helper components ----

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
        checked ? 'bg-teal-500' : 'bg-slate-600'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
          checked ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
        } mt-0.5`}
      />
    </button>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
  icon,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs sm:text-sm text-slate-300">{label}</span>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-xs sm:text-sm text-slate-400 shrink-0">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="w-24 rounded bg-slate-900 border border-slate-600 px-3 py-1.5 text-sm text-white text-right focus:border-teal-400 focus:outline-none"
      />
    </div>
  );
}

interface HelpEntry {
  key: string;
  title: string;
  description: string;
  commands: string[];
}

function getHelpEntries(caps: SleepCapabilities): HelpEntry[] {
  const entries: HelpEntry[] = [];
  if (!caps.hdparm_available) {
    entries.push({
      key: 'hdparm',
      title: 'hdparm — Disk Spindown Tool',
      description: 'Required to spin down data disks during sleep.',
      commands: ['sudo apt install hdparm', 'hdparm -C /dev/sdX   # verify standby support'],
    });
  }
  if (!caps.can_suspend) {
    entries.push({
      key: 'suspend',
      title: 'Suspend (S3 Sleep)',
      description: 'System must support S3 suspend-to-RAM.',
      commands: ['cat /sys/power/state   # should contain "mem"', '# If missing: enable S3 (Suspend to RAM) in BIOS/UEFI'],
    });
  }
  if (caps.wol_interfaces.length === 0) {
    entries.push({
      key: 'wol',
      title: 'Wake-on-LAN',
      description: 'Requires ethtool and a NIC with WoL support. Also enable WoL in BIOS.',
      commands: [
        'sudo apt install ethtool',
        'sudo ethtool -s <iface> wol g',
        '# Persistent (systemd-networkd):',
        '# /etc/systemd/network/10-<iface>.link',
        '# [Link]',
        '# WakeOnLan=magic',
      ],
    });
  }
  if (!caps.rtcwake_available) {
    entries.push({
      key: 'rtcwake',
      title: 'rtcwake — Timed Wake-up',
      description: 'Part of util-linux (usually pre-installed).',
      commands: ['ls /dev/rtc*   # check for RTC device', 'sudo apt install util-linux'],
    });
  }
  if (!caps.systemctl_available) {
    entries.push({
      key: 'systemctl',
      title: 'systemctl — Systemd Control',
      description: 'Part of systemd (pre-installed on Debian/Ubuntu).',
      commands: ['systemctl --version   # verify installation', 'sudo apt install systemd'],
    });
  }
  return entries;
}

function CapabilityHelp({
  capabilities,
  open,
  onToggle,
}: {
  capabilities: SleepCapabilities;
  open: boolean;
  onToggle: () => void;
}) {
  const entries = getHelpEntries(capabilities);
  if (entries.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
      >
        <Terminal className="h-3.5 w-3.5" />
        Setup Help
        <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      <div
        className={`grid transition-[grid-template-rows] duration-200 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <div className="pt-3 space-y-3">
            {entries.map((entry) => (
              <div key={entry.key} className="rounded-lg bg-slate-800/60 border border-slate-700/40 p-3">
                <h5 className="text-xs font-medium text-slate-200 mb-1">{entry.title}</h5>
                <p className="text-xs text-slate-400 mb-2">{entry.description}</p>
                <pre className="bg-slate-900/80 border border-slate-700/50 rounded px-3 py-2 font-mono text-xs text-slate-300 overflow-x-auto">
                  {entry.commands.join('\n')}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function CapBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        ok ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700/50 text-slate-500'
      }`}
    >
      {ok ? '\u2713' : '\u2717'} {label}
    </span>
  );
}
