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

  // Stable refs to avoid re-creating callbacks when props change
  const onLogoutRef = useRef(onLogout);
  onLogoutRef.current = onLogout;

  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const idleTimer = useRef<ReturnType<typeof setTimeout>>();
  const countdownInterval = useRef<ReturnType<typeof setInterval>>();
  const warningActiveRef = useRef(false);

  const clearTimers = useCallback(() => {
    if (idleTimer.current) { clearTimeout(idleTimer.current); idleTimer.current = undefined; }
    if (countdownInterval.current) { clearInterval(countdownInterval.current); countdownInterval.current = undefined; }
  }, []);

  const resetTimer = useCallback(() => {
    clearTimers();
    warningActiveRef.current = false;
    setWarningVisible(false);
    setSecondsRemaining(WARNING_SEC);

    if (!enabledRef.current) return;

    idleTimer.current = setTimeout(() => {
      // Show warning, start countdown
      warningActiveRef.current = true;
      setWarningVisible(true);
      let remaining = WARNING_SEC;
      setSecondsRemaining(remaining);

      countdownInterval.current = setInterval(() => {
        remaining -= 1;
        setSecondsRemaining(remaining);
        if (remaining <= 0) {
          clearTimers();
          warningActiveRef.current = false;
          onLogoutRef.current();
        }
      }, 1000);
    }, IDLE_MS);
  }, [clearTimers]);

  // Activity handler — resets timer and pings other tabs
  const handleActivity = useCallback(() => {
    // Ignore activity while warning is showing — user must click "Stay logged in"
    if (warningActiveRef.current) return;
    resetTimer();
    try {
      localStorage.setItem(STORAGE_KEY, Date.now().toString());
    } catch { /* quota errors are harmless */ }
  }, [resetTimer]);

  // Register DOM activity listeners
  useEffect(() => {
    if (!enabled) {
      clearTimers();
      warningActiveRef.current = false;
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
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cross-tab sync: listen for storage events from other tabs
  useEffect(() => {
    if (!enabled) return;

    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && !warningActiveRef.current) {
        resetTimer();
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return { warningVisible, secondsRemaining, resetTimer };
}
