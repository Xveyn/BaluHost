import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import type { ForeignInhibitorStatus } from '../../../api/sleep';

type ForeignInhibitorNoticeProps = {
  inhibitor: ForeignInhibitorStatus | null;
};

/**
 * Names the third-party program currently blocking automatic suspend (#602).
 *
 * Without this the box simply never sleeps and nothing says why, which reads
 * as a hang rather than as another program getting its way. The PID is shown
 * because that is what you need to track the holder down.
 *
 * `who`, `why` and `pid` are rendered as plain nodes rather than through
 * interpolation: a missing placeholder in a locale file is invisible in tests,
 * since the i18n mock fabricates interpolation that the real JSON may not have.
 */
export function ForeignInhibitorNotice({ inhibitor }: ForeignInhibitorNoticeProps) {
  const { t } = useTranslation('system');
  if (!inhibitor) return null;

  return (
    <div className="card border-amber-500/30 bg-amber-500/5 p-4 sm:p-6 space-y-2">
      <h4 className="text-sm font-medium text-amber-300 flex items-center gap-2">
        <Lock className="h-4 w-4" />
        {t('sleep.foreignInhibitor.title')}
      </h4>
      <p className="text-xs text-slate-400">{t('sleep.foreignInhibitor.description')}</p>
      <p className="text-sm text-white">
        <span className="font-mono">{inhibitor.who}</span>
        {' — '}
        {inhibitor.why}
      </p>
      <p className="text-xs text-slate-500">
        {t('sleep.foreignInhibitor.detailsLabel')}{' '}
        <span className="font-mono">{inhibitor.what}</span>
        {', PID '}
        <span className="font-mono">{inhibitor.pid}</span>
      </p>
    </div>
  );
}
