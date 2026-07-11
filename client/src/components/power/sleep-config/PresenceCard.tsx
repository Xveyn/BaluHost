import { useTranslation } from 'react-i18next';
import { Eye } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { PresenceMode, PresenceStatus } from '../../../api/sleep';

type PresenceCardProps = Pick<SleepConfigForm, 'presenceEnabled' | 'presenceMode' | 'presenceTimeout'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  presenceStatus: PresenceStatus | null;
};

export function PresenceCard({ presenceEnabled, presenceMode, presenceTimeout, update, presenceStatus }: PresenceCardProps) {
  const { t } = useTranslation('system');
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Eye className="h-4 w-4 text-emerald-400" />
          {t('sleep.presence.title')}
        </h4>
        <Toggle checked={presenceEnabled} onChange={(v) => update({ presenceEnabled: v })} />
      </div>
      <p className="text-xs text-slate-400">{t('sleep.presence.description')}</p>

      {presenceEnabled && (
        <div className="space-y-3 pl-1">
          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('sleep.presence.modeLabel')}</label>
            <select
              value={presenceMode}
              onChange={(e) => update({ presenceMode: e.target.value as PresenceMode })}
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
            >
              <option value="active">{t('sleep.presence.modeActive')}</option>
              <option value="session">{t('sleep.presence.modeSession')}</option>
            </select>
            <p className="mt-1 text-xs text-slate-500">{t('sleep.presence.modeHint')}</p>
          </div>
          <NumberInput
            label={t('sleep.presence.timeoutLabel')}
            value={presenceTimeout}
            onChange={(v) => update({ presenceTimeout: v })}
            min={1}
            max={60}
          />
          {presenceStatus?.suppressing_suspend && (
            <div className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-300">
              {t('sleep.presence.suppressing', { count: presenceStatus.active_session_count })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
