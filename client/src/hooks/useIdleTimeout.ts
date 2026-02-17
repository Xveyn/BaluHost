import { useState, useEffect, useRef, useCallback } from 'react';

const IDLE_MS = 4 * 60 * 1000;       // 4 min until warning
const WARNING_SEC = 60;                // 60s countdown
const STORAGE_KEY = 'baluhost-idle-ping';
const ACTIVITY_EVENTS: (keyof DocumentEventMap)[] = [
  'mousemove', 'keydown', 'click', 'scroll', 'touchstart',
];

interface UseIdleTimeoutOptions {
  onLogout: () => void;
  enabled: boolean;
}

interface UseIdleTimeoutReturn {
  warningVisible: boolean;
  secondsRemaining: number;
  resetTimer: () => void;
}

export function useIdleTimeout({ onLogout, enabled }: UseIdleTimeoutOptions): UseIdleTimeoutReturn {
  const [warningVisible, setWarningVisible] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(WARNING_SEC);

  const idleTimer = useRef<ReturnType<typeof setTimeout>>();
  const countdownInterval = useRef<ReturnType<typeof setInterval>>();
  const secondsRef = useRef(WARNING_SEC);

  const clearTimers = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    if (countdownInterval.current) clearInterval(countdownInterval.current);
  }, []);

  const resetTimer = useCallback(() => {
    clearTimers();
    setWarningVisible(false);
    setSecondsRemaining(WARNING_SEC);
    secondsRef.current = WARNING_SEC;

    if (!enabled) return;

    idleTimer.current = setTimeout(() => {
      // Show warning, start countdown
      setWarningVisible(true);
      secondsRef.current = WARNING_SEC;
      setSecondsRemaining(WARNING_SEC);

      countdownInterval.current = setInterval(() => {
        secondsRef.current -= 1;
        setSecondsRemaining(secondsRef.current);
        if (secondsRef.current <= 0) {
          clearTimers();
          onLogout();
        }
      }, 1000);
    }, IDLE_MS);
  }, [enabled, onLogout, clearTimers]);

  // Activity handler — resets timer and pings other tabs
  const handleActivity = useCallback(() => {
    // Only reset if warning is NOT showing (activity during warning is ignored;
    // user must explicitly click "Stay logged in")
    if (secondsRef.current < WARNING_SEC && secondsRef.current > 0) return;
    resetTimer();
    // Cross-tab sync: write timestamp so other tabs pick it up
    try {
      localStorage.setItem(STORAGE_KEY, Date.now().toString());
    } catch { /* quota errors are harmless */ }
  }, [resetTimer]);

  // Register DOM activity listeners
  useEffect(() => {
    if (!enabled) {
      clearTimers();
      setWarningVisible(false);
      return;
    }

    // Start the idle timer immediately
    resetTimer();

    for (const event of ACTIVITY_EVENTS) {
      document.addEventListener(event, handleActivity, { passive: true });
    }

    return () => {
      clearTimers();
      for (const event of ACTIVITY_EVENTS) {
        document.removeEventListener(event, handleActivity);
      }
    };
  }, [enabled, handleActivity, resetTimer, clearTimers]);

  // Cross-tab sync: listen for storage events from other tabs
  useEffect(() => {
    if (!enabled) return;

    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        resetTimer();
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [enabled, resetTimer]);

  return { warningVisible, secondsRemaining, resetTimer };
}
