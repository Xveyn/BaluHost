import { useTranslation } from 'react-i18next';
import { Gamepad2 } from 'lucide-react';
import { Toggle } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { GamingStatus } from '../../../api/sleep';

type GamingCardProps = Pick<SleepConfigForm, 'blockSuspendInGamingMode'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  gamingStatus: GamingStatus | null;
};

/**
 * Gaming as a suspend suppressor.
 *
 * A running game always blocks and therefore has no toggle — the toggle
 * governs only Big Picture with no game behind it, which is the ambiguous
 * case (someone browsing the library vs. a screen left on).
 */
export function GamingCard({ blockSuspendInGamingMode, update, gamingStatus }: GamingCardProps) {
  const { t } = useTranslation('system');
  const gameRunning = gamingStatus?.game_running ?? false;
  // Big Picture is only worth reporting on its own; with a game running the
  // game is the more specific and more useful statement.
  const bigPictureOnly = !gameRunning && (gamingStatus?.gaming_mode ?? false);

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Gamepad2 className="h-4 w-4 text-violet-400" />
        {t('sleep.gaming.title')}
      </h4>
      <p className="text-xs text-slate-400">{t('sleep.gaming.description')}</p>

      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm text-white">{t('sleep.gaming.bigPictureLabel')}</p>
          <p className="text-xs text-slate-500">{t('sleep.gaming.bigPictureHint')}</p>
        </div>
        <Toggle
          checked={blockSuspendInGamingMode}
          onChange={(v) => update({ blockSuspendInGamingMode: v })}
        />
      </div>

      {gameRunning && (
        <div className="rounded border border-violet-500/20 bg-violet-500/10 p-2 text-xs text-violet-300">
          {t('sleep.gaming.gameRunning')}
        </div>
      )}
      {bigPictureOnly && (
        <div className="rounded border border-violet-500/20 bg-violet-500/10 p-2 text-xs text-violet-300">
          {gamingStatus?.suppressing_suspend
            ? t('sleep.gaming.bigPictureActive')
            : t('sleep.gaming.bigPictureIgnored')}
        </div>
      )}
    </div>
  );
}
