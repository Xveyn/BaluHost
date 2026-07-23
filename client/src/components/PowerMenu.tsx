import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Power, PowerOff, RotateCcw, LogOut, Moon, Pause, MonitorOff, Monitor, Plug } from 'lucide-react';
import { ConfirmDialog } from './ui/ConfirmDialog';
import { getSleepStatus, enterSoftSleep, enterSuspend } from '../api/sleep';
import { getDesktopStatus, disableDesktop, enableDesktop, type DesktopState } from '../api/desktop';
import { usePlugins } from '../contexts/PluginContext';
import { runPluginMenuAction } from '../api/plugins';
import { resolvePluginString } from '../lib/pluginI18n';
import { resolveIcon } from './topbar/iconMap';
import toast from 'react-hot-toast';

interface PowerMenuProps {
  isAdmin: boolean;
  onShutdown: () => Promise<void>;
  onRestart: () => Promise<void>;
  onLogout: () => void;
}

export default function PowerMenu({ isAdmin, onShutdown, onRestart, onLogout }: PowerMenuProps) {
  const { t } = useTranslation('common');
  const [isOpen, setIsOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<'shutdown' | 'restart' | 'sleep' | 'suspend' | null>(null);
  const [sleepAvailable, setSleepAvailable] = useState(false);
  const [desktopState, setDesktopState] = useState<DesktopState | null>(null);
  const { pluginMenuItems } = usePlugins();
  const [runningAction, setRunningAction] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Check sleep + desktop availability when dropdown opens. Both states are
  // intentionally kept from the previous open and re-fetched on every open, so
  // there is no flash of a missing item during the re-fetch.
  useEffect(() => {
    if (isOpen && isAdmin) {
      getSleepStatus()
        .then(() => setSleepAvailable(true))
        .catch(() => setSleepAvailable(false));
      getDesktopStatus()
        .then((s) => setDesktopState(s.state))
        .catch(() => setDesktopState(null));
    }
  }, [isOpen, isAdmin]);

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
    } else if (action === 'sleep') {
      try {
        await enterSoftSleep();
        toast.success(t('powerMenu.sleepActivated', 'Sleep mode activated'));
      } catch {
        toast.error(t('powerMenu.sleepFailed', 'Failed to enter sleep mode'));
      }
    } else if (action === 'suspend') {
      try {
        await enterSuspend();
        toast.success(t('powerMenu.suspendActivated', 'System suspended'));
      } catch {
        toast.error(t('powerMenu.suspendFailed', 'Failed to suspend system'));
      }
    }
  };

  const handleDisableDesktop = async () => {
    setIsOpen(false);
    try {
      const result = await disableDesktop();
      if (result.success) {
        toast.success(t('powerMenu.desktopDisabled', 'Desktop disabled'));
      } else {
        toast.error(result.message || t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
      }
    } catch {
      toast.error(t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
    }
  };

  const handleEnableDesktop = async () => {
    setIsOpen(false);
    try {
      const result = await enableDesktop();
      if (result.success) {
        toast.success(t('powerMenu.desktopEnabled', 'Desktop enabled'));
      } else {
        toast.error(result.message || t('powerMenu.desktopEnableFailed', 'Failed to enable desktop'));
      }
    } catch {
      toast.error(t('powerMenu.desktopEnableFailed', 'Failed to enable desktop'));
    }
  };

  const handlePluginAction = async (item: (typeof pluginMenuItems)[number]) => {
    const key = `${item._pluginName}:${item.id}`;
    setRunningAction(key);
    try {
      const result = await runPluginMenuAction(item._pluginName, item.id);
      const message = resolvePluginString(
        item._translations,
        result.message_key ?? '',
        result.message_text,
      );
      if (result.ok) {
        toast.success(message);
        setIsOpen(false);
      } else {
        toast.error(message);
      }
    } catch {
      toast.error(t('powerMenu.pluginActionFailed', 'Action failed'));
    } finally {
      setRunningAction(null);
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
                      <p className="text-xs text-slate-400">{t('powerMenu.restartDesc', 'Restart BaluHost')}</p>
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
                      <p className="text-xs text-slate-400">{t('powerMenu.shutdownDesc', 'Shut down BaluHost')}</p>
                    </div>
                  </button>

                  {sleepAvailable && (
                    <>
                      <button
                        onClick={() => { setConfirmAction('sleep'); }}
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-blue-500/10"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-500/30 bg-blue-500/10">
                          <Moon className="h-4 w-4 text-blue-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-100">{t('powerMenu.sleep', 'Sleep')}</p>
                          <p className="text-xs text-slate-400">{t('powerMenu.sleepDesc', 'Enter sleep mode')}</p>
                        </div>
                      </button>

                      <button
                        onClick={() => { setConfirmAction('suspend'); }}
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-purple-500/10"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-purple-500/30 bg-purple-500/10">
                          <Pause className="h-4 w-4 text-purple-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-100">{t('powerMenu.suspend', 'Standby')}</p>
                          <p className="text-xs text-slate-400">{t('powerMenu.suspendDesc', 'Suspend system')}</p>
                        </div>
                      </button>
                    </>
                  )}

                  {desktopState === 'running' && (
                    <button
                      onClick={handleDisableDesktop}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-cyan-500/10"
                    >
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
                        <MonitorOff className="h-4 w-4 text-cyan-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-100">{t('powerMenu.desktopDisable', 'Disable desktop')}</p>
                        <p className="text-xs text-slate-400">{t('powerMenu.desktopDisableDesc', 'Turn off displays (saves GPU power)')}</p>
                      </div>
                    </button>
                  )}

                  {desktopState === 'stopped' && (
                    <button
                      onClick={handleEnableDesktop}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-emerald-500/10"
                    >
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10">
                        <Monitor className="h-4 w-4 text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-100">{t('powerMenu.desktopEnable', 'Enable desktop')}</p>
                        <p className="text-xs text-slate-400">{t('powerMenu.desktopEnableDesc', 'Turn displays back on')}</p>
                      </div>
                    </button>
                  )}

                  {pluginMenuItems.map((item) => {
                    const Icon = resolveIcon(item.icon) ?? Plug;
                    const key = `${item._pluginName}:${item.id}`;
                    const label = resolvePluginString(item._translations, item.label_key, item.label_text);
                    const description = item.description_key
                      ? resolvePluginString(item._translations, item.description_key, item.description_text ?? '')
                      : item.description_text;
                    return (
                      <button
                        key={key}
                        onClick={() => { void handlePluginAction(item); }}
                        disabled={runningAction !== null}
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-sky-500/10 disabled:opacity-50"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-sky-500/30 bg-sky-500/10">
                          <Icon className="h-4 w-4 text-sky-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-100">{label}</p>
                          {description && <p className="text-xs text-slate-400">{description}</p>}
                        </div>
                      </button>
                    );
                  })}
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
        message={t('powerMenu.shutdownConfirm', 'Shut down BaluHost? All services will be stopped.')}
        confirmLabel={t('powerMenu.shutdown', 'Shutdown')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="danger"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      <ConfirmDialog
        open={confirmAction === 'restart'}
        title={t('powerMenu.restart', 'Restart')}
        message={t('powerMenu.restartConfirm', 'Restart BaluHost? All services will be briefly interrupted.')}
        confirmLabel={t('powerMenu.restart', 'Restart')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="warning"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      <ConfirmDialog
        open={confirmAction === 'sleep'}
        title={t('powerMenu.sleep', 'Sleep')}
        message={t('powerMenu.sleepConfirm', 'Enter sleep mode? Services will be paused, but the server remains reachable.')}
        confirmLabel={t('powerMenu.sleep', 'Sleep')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="warning"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      <ConfirmDialog
        open={confirmAction === 'suspend'}
        title={t('powerMenu.suspend', 'Standby')}
        message={t('powerMenu.suspendConfirm', 'Suspend the system? The server will be unreachable until woken up.')}
        confirmLabel={t('powerMenu.suspend', 'Standby')}
        cancelLabel={t('buttons.cancel', 'Cancel')}
        variant="danger"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />
    </>
  );
}
