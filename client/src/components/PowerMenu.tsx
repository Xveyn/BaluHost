import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Power, PowerOff, RotateCcw, LogOut } from 'lucide-react';
import { ConfirmDialog } from './ui/ConfirmDialog';

interface PowerMenuProps {
  isAdmin: boolean;
  onShutdown: () => Promise<void>;
  onRestart: () => Promise<void>;
  onLogout: () => void;
}

export default function PowerMenu({ isAdmin, onShutdown, onRestart, onLogout }: PowerMenuProps) {
  const { t } = useTranslation('common');
  const [isOpen, setIsOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<'shutdown' | 'restart' | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleConfirm = async () => {
    const action = confirmAction;
    setConfirmAction(null);
    setIsOpen(false);

    if (action === 'shutdown') {
      await onShutdown();
    } else if (action === 'restart') {
      await onRestart();
    }
  };

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        {/* Power Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-400 transition hover:border-rose-400/50 hover:bg-rose-500/20"
          title={t('powerMenu.title', 'Power')}
        >
          <Power className="h-5 w-5" />
        </button>

        {/* Dropdown */}
        {isOpen && (
          <div className="absolute right-0 top-12 z-50 w-60 rounded-xl border border-slate-800 bg-slate-900/90 shadow-xl backdrop-blur-xl">
            {/* Admin actions */}
            {isAdmin && (
              <>
                <div className="p-1.5">
                  <button
                    onClick={() => { setConfirmAction('restart'); }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-amber-500/10"
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10">
                      <RotateCcw className="h-4 w-4 text-amber-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-100">{t('powerMenu.restart', 'Restart')}</p>
                      <p className="text-xs text-slate-400">{t('powerMenu.restartDesc', 'Restart server')}</p>
                    </div>
                  </button>

                  <button
                    onClick={() => { setConfirmAction('shutdown'); }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-rose-500/10"
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-rose-500/30 bg-rose-500/10">
                      <PowerOff className="h-4 w-4 text-rose-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-100">{t('powerMenu.shutdown', 'Shutdown')}</p>
                      <p className="text-xs text-slate-400">{t('powerMenu.shutdownDesc', 'Shut down server')}</p>
                    </div>
                  </button>
                </div>

                <div className="mx-3 border-t border-slate-800" />
              </>
            )}

            {/* Logout (always visible) */}
            <div className="p-1.5">
              <button
                onClick={() => { setIsOpen(false); onLogout(); }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-slate-800/50"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 bg-slate-800/50">
                  <LogOut className="h-4 w-4 text-slate-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-100">{t('powerMenu.logout', 'Logout')}</p>
                </div>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Confirm Dialogs */}
      <ConfirmDialog
        open={confirmAction === 'shutdown'}
        title={t('powerMenu.shutdown', 'Shutdown')}
        message={t('powerMenu.shutdownConfirm', 'Shut down the server? All services will be stopped.')}
        confirmLabel={t('powerMenu.shutdown', 'Shutdown')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="danger"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      <ConfirmDialog
        open={confirmAction === 'restart'}
        title={t('powerMenu.restart', 'Restart')}
        message={t('powerMenu.restartConfirm', 'Restart the server? All services will be briefly interrupted.')}
        confirmLabel={t('powerMenu.restart', 'Restart')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="warning"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />
    </>
  );
}
