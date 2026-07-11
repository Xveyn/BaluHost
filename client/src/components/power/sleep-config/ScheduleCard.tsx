import { useTranslation } from 'react-i18next';
import { Clock } from 'lucide-react';
import { Toggle } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { ScheduleMode } from '../../../api/sleep';

type ScheduleCardProps = Pick<
  SleepConfigForm,
  'scheduleEnabled' | 'scheduleSleepTime' | 'scheduleWakeTime' | 'scheduleMode'
> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  coreUptimeMasterOn: boolean;
  alwaysAwakeOn: boolean;
};

export function ScheduleCard({
  scheduleEnabled, scheduleSleepTime, scheduleWakeTime, scheduleMode, update, coreUptimeMasterOn, alwaysAwakeOn,
}: ScheduleCardProps) {
  const { t } = useTranslation('system');
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Clock className="h-4 w-4 text-amber-400" />
          Sleep Schedule
        </h4>
        <Toggle checked={scheduleEnabled} onChange={(v) => update({ scheduleEnabled: v })} />
      </div>

      {scheduleEnabled && (
        <div className="space-y-3 pl-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Sleep at</label>
              <input
                type="time"
                value={scheduleSleepTime}
                onChange={(e) => update({ scheduleSleepTime: e.target.value })}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Wake at</label>
              <input
                type="time"
                value={scheduleWakeTime}
                onChange={(e) => update({ scheduleWakeTime: e.target.value })}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Schedule Mode</label>
            <select
              value={scheduleMode}
              onChange={(e) => update({ scheduleMode: e.target.value as ScheduleMode })}
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
            >
              <option value="soft">Soft Sleep</option>
              <option value="suspend">True Suspend</option>
            </select>
          </div>
          {coreUptimeMasterOn && (
            <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.coreUptime.scheduleOverride')}
            </div>
          )}
          {alwaysAwakeOn && (
            <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.alwaysAwake.scheduleHint')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
