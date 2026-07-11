import { Timer } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type IdleDetectionCardProps = Pick<
  SleepConfigForm,
  'autoIdleEnabled' | 'idleTimeout' | 'idleCpuThreshold' | 'idleDiskIoThreshold' | 'idleHttpThreshold'
> & { update: (patch: Partial<SleepConfigForm>) => void };

export function IdleDetectionCard({
  autoIdleEnabled, idleTimeout, idleCpuThreshold, idleDiskIoThreshold, idleHttpThreshold, update,
}: IdleDetectionCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Timer className="h-4 w-4 text-blue-400" />
          Auto-Idle Detection
        </h4>
        <Toggle checked={autoIdleEnabled} onChange={(v) => update({ autoIdleEnabled: v })} />
      </div>

      {autoIdleEnabled && (
        <div className="space-y-3 pl-1">
          <NumberInput label="Idle timeout (min)" value={idleTimeout} onChange={(v) => update({ idleTimeout: v })} min={1} max={1440} />
          <NumberInput label="CPU threshold (%)" value={idleCpuThreshold} onChange={(v) => update({ idleCpuThreshold: v })} min={0} max={100} step={0.5} />
          <NumberInput label="Disk I/O threshold (MB/s)" value={idleDiskIoThreshold} onChange={(v) => update({ idleDiskIoThreshold: v })} min={0} step={0.1} />
          <NumberInput label="HTTP req/min threshold" value={idleHttpThreshold} onChange={(v) => update({ idleHttpThreshold: v })} min={0} step={1} />
        </div>
      )}
    </div>
  );
}
