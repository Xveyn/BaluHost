import { useTranslation } from 'react-i18next';
import { ShieldAlert } from 'lucide-react';
import { useTwoFactorStatus } from './twoFactorStatusStore';

export interface TwoFactorPromptSectionProps {
  onOpenSetup: () => void;
}

export function TwoFactorPromptSection({ onOpenSetup }: TwoFactorPromptSectionProps) {
  const { t } = useTranslation('common');
  const status = useTwoFactorStatus(true);

  // Loading or enabled or error → render nothing
  if (status === null || status.enabled) return null;

  return (
    <>
      <div className="border-t border-slate-800/70 my-1" />
      <section className="px-3 py-2">
        <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-amber-300">
          <ShieldAlert className="w-3.5 h-3.5" />
          {t('userMenu.quickSettings.twoFactor.notEnabled')}
        </div>
        <button
          type="button"
          onClick={onOpenSetup}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-sm font-medium text-amber-200 hover:bg-amber-500/20 transition"
        >
          {t('userMenu.quickSettings.twoFactor.enableNow')}
        </button>
      </section>
    </>
  );
}
