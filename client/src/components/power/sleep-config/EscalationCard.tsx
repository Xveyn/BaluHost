import { TrendingUp } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type EscalationCardProps = Pick<SleepConfigForm, 'escalationEnabled' | 'escalationMinutes'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
};

export function EscalationCard({ escalationEnabled, escalationMinutes, update }: EscalationCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-purple-400" />
          Auto-Escalation (Soft Sleep → Suspend)
        </h4>
        <Toggle checked={escalationEnabled} onChange={(v) => update({ escalationEnabled: v })} />
      </div>

      {escalationEnabled && (
        <div className="pl-1">
          <NumberInput label="Escalate after (min)" value={escalationMinutes} onChange={(v) => update({ escalationMinutes: v })} min={1} max={1440} />
        </div>
      )}
    </div>
  );
}
