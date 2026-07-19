import { useTranslation } from 'react-i18next';
import type { PendingPowerAction } from '../../hooks/usePowerActions';

interface PendingPowerOverlayProps {
  action: PendingPowerAction;
  message: string | null;
}

export function PendingPowerOverlay({ action, message }: PendingPowerOverlayProps) {
  const { t } = useTranslation('common');
  if (!action) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4 rounded-2xl bg-slate-900/90 border border-slate-800 p-6">
        <div className={`h-12 w-12 flex items-center justify-center rounded-full ${action === 'restart' ? 'bg-amber-500/10 text-amber-400' : 'bg-rose-500/10 text-rose-400'}`}>
          <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none" strokeWidth={2}>
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 2v4M12 18v4M4.2 4.2l2.8 2.8M17 17l2.8 2.8M2 12h4M18 12h4M4.2 19.8l2.8-2.8M17 7l2.8-2.8" />
          </svg>
        </div>
        <div className="text-center">
          <p className="font-semibold">{action === 'restart' ? t('powerMenu.restarting', 'Restarting...') : t('powerMenu.shuttingDown', 'Shutting down...')}</p>
          <p className="text-sm text-slate-100-tertiary">{message}</p>
        </div>
      </div>
    </div>
  );
}
