import { Server, HardDrive } from 'lucide-react';
import { ToggleRow, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type SleepBehaviorCardProps = Pick<
  SleepConfigForm,
  'pauseMonitoring' | 'pauseDiskIo' | 'diskSpindown' | 'reducedTelemetry'
> & { update: (patch: Partial<SleepConfigForm>) => void };

export function SleepBehaviorCard({ pauseMonitoring, pauseDiskIo, diskSpindown, reducedTelemetry, update }: SleepBehaviorCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Server className="h-4 w-4 text-teal-400" />
        Sleep Behavior
      </h4>
      <div className="space-y-3">
        <ToggleRow label="Pause monitoring" checked={pauseMonitoring} onChange={(v) => update({ pauseMonitoring: v })} />
        <ToggleRow label="Pause disk I/O monitor" checked={pauseDiskIo} onChange={(v) => update({ pauseDiskIo: v })} />
        <ToggleRow
          label="Spin down data disks"
          checked={diskSpindown}
          onChange={(v) => update({ diskSpindown: v })}
          icon={<HardDrive className="h-3.5 w-3.5 text-slate-400" />}
        />
        <NumberInput
          label="Reduced telemetry interval (s)"
          value={reducedTelemetry}
          onChange={(v) => update({ reducedTelemetry: v })}
          min={5}
          max={300}
        />
      </div>
    </div>
  );
}
