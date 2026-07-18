import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { localApi } from '../lib/localApi';

export type PendingPowerAction = 'shutdown' | 'restart' | null;

export function usePowerActions(logout: () => void) {
  const { t } = useTranslation('common');
  const [pendingAction, setPendingAction] = useState<PendingPowerAction>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const timeoutsRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Guards a poll tick that is already suspended at `await localApi.isAvailable()`
  // when unmount happens: clearInterval only stops *future* ticks, it does not
  // abort one already in flight. Checked immediately after that await.
  const mountedRef = useRef(true);

  // Cleanup bei Unmount: Ist-Code leakte Intervall/Timeouts (Layout.tsx:579-594)
  useEffect(() => () => {
    mountedRef.current = false;
    timeoutsRef.current.forEach(clearTimeout);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  const later = (fn: () => void, ms: number) => {
    timeoutsRef.current.push(setTimeout(fn, ms));
  };

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const onShutdown = async () => {
    setPendingAction('shutdown');
    setPendingMessage(t('powerMenu.shutdownStarted', 'Shutdown initiated...'));
    try {
      const res = await localApi.shutdown();
      const eta = (res && typeof res === 'object' && 'eta_seconds' in res ? (res as { eta_seconds: number }).eta_seconds : 1);
      setPendingMessage(t('powerMenu.shutdownEta', 'Shutdown scheduled — stopping in ~{{eta}}s', { eta }));
      later(() => {
        setPendingAction(null);
        logout();
      }, (eta + 1) * 1000);
    } catch {
      setPendingMessage(t('powerMenu.shuttingDown', 'Shutting down...'));
      later(() => {
        setPendingAction(null);
        logout();
      }, 2000);
    }
  };

  const onRestart = async () => {
    setPendingAction('restart');
    setPendingMessage(t('powerMenu.restartStarted', 'Restart initiated...'));
    try {
      await localApi.restart();
      setPendingMessage(t('powerMenu.restartingWait', 'Restarting — waiting for server...'));
      const startTime = Date.now();
      intervalRef.current = setInterval(async () => {
        const available = await localApi.isAvailable();
        if (!mountedRef.current) return;
        if (available) {
          stopPolling();
          setPendingAction(null);
          window.location.reload();
        }
        if (Date.now() - startTime > 60000) {
          stopPolling();
          setPendingAction(null);
          setPendingMessage(null);
          logout();
        }
      }, 2000);
    } catch {
      setPendingMessage(t('powerMenu.restartingWait', 'Restarting — waiting for server...'));
      later(() => {
        setPendingAction(null);
        logout();
      }, 5000);
    }
  };

  return { pendingAction, pendingMessage, onShutdown, onRestart };
}
