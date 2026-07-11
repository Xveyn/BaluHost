import { Settings, Terminal, ChevronDown } from 'lucide-react';
import type { SleepCapabilities } from '../../../api/sleep';

export function CapabilitiesCard({
  capabilities,
  helpOpen,
  onToggleHelp,
}: {
  capabilities: SleepCapabilities;
  helpOpen: boolean;
  onToggleHelp: () => void;
}) {
  return (
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
      <CapabilityHelp capabilities={capabilities} open={helpOpen} onToggle={onToggleHelp} />
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
      {ok ? '✓' : '✗'} {label}
    </span>
  );
}
