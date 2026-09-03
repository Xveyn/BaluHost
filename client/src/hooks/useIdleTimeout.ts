import { useState, useEffect, useRef, useCallback } from 'react';
import { DEFAULT_IDLE_MS, DEFAULT_WARNING_SEC } from '../lib/sessionDefaults';

const STORAGE_KEY = 'baluhost-idle-ping';
const ACTIVITY_EVENTS: (keyof DocumentEventMap)[] = [
  'mousemove', 'keydown', 'click', 'scroll', 'touchstart',
];

interface UseIdleTimeoutOptions {
  onLogout: () => void;
  enabled: boolean;
  /** Inactivity before the warning appears. Defaults to 4 min. */
  idleMs?: number;
  /** Countdown length inside the warning dialog. Defaults to 60 s. */
  warningSec?: number;
}

interface UseIdleTimeoutReturn {
  warningVisible: boolean;
  secondsRemaining: number;
  resetTimer: () => void;
}

export function useIdleTimeout({
  onLogout,
  enabled,
  idleMs = DEFAULT_IDLE_MS,
  warningSec = DEFAULT_WARNING_SEC,
}: UseIdleTimeoutOptions): UseIdleTimeoutReturn {
  const [warningVisible, setWarningVisible] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(warningSec);

  // Stable refs to avoid re-creating callbacks when props change
  const onLogoutRef = useRef(onLogout);
  onLogoutRef.current = onLogout;

  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  // The durations arrive from the server one render after login, so callbacks
  // read them through refs and stay stable; the effect below restarts the
  // timers when they actually change.
  const idleMsRef = useRef(idleMs);
  idleMsRef.current = idleMs;
  const warningSecRef = useRef(warningSec);
  warningSecRef.current = warningSec;

  const idleTimer = useRef<ReturnType<typeof setTimeout>>();
  const countdownInterval = useRef<ReturnType<typeof setInterval>>();
  const warningActiveRef = useRef(false);
  const lastActivityRef = useRef<number>(Date.now());

  const clearTimers = useCallback(() => {
    if (idleTimer.current) { clearTimeout(idleTimer.current); idleTimer.current = undefined; }
    if (countdownInterval.current) { clearInterval(countdownInterval.current); countdownInterval.current = undefined; }
  }, []);

  const startCountdown = useCallback((seconds: number) => {
    warningActiveRef.current = true;
    setWarningVisible(true);
    let remaining = seconds;
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
  }, [clearTimers]);

  const resetTimer = useCallback(() => {
    clearTimers();
    warningActiveRef.current = false;
    setWarningVisible(false);
    setSecondsRemaining(warningSecRef.current);
    lastActivityRef.current = Date.now();

    if (!enabledRef.current) return;

    idleTimer.current = setTimeout(() => {
      startCountdown(warningSecRef.current);
    }, idleMsRef.current);
  }, [clearTimers, startCountdown]);

  // Activity handler — resets timer and pings other tabs
  const handleActivity = useCallback(() => {
    // Ignore activity while warning is showing — user must click "Stay logged in"
    if (warningActiveRef.current) return;
    lastActivityRef.current = Date.now();
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
    // idleMs/warningSec are in the deps on purpose: when the server-side policy
    // arrives after login, the running timer must be replaced, not left at the
    // fallback duration.
  }, [enabled, idleMs, warningSec]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Mobile browser fix: JS timers freeze when backgrounded.
  // On resume, check real elapsed time and act accordingly.
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;

      const elapsed = Date.now() - lastActivityRef.current;
      const totalMs = idleMsRef.current + warningSecRef.current * 1000;

      if (elapsed >= totalMs) {
        // Total timeout elapsed → immediate logout
        clearTimers();
        warningActiveRef.current = false;
        onLogoutRef.current();
      } else if (elapsed >= idleMsRef.current) {
        // Idle time passed, still in countdown window → show warning with adjusted countdown
        clearTimers();
        const remaining = Math.ceil((totalMs - elapsed) / 1000);
        startCountdown(remaining);
      } else {
        // Not yet expired → restart timer with remaining idle time
        if (!warningActiveRef.current) {
          clearTimers();
          const remainingIdle = idleMsRef.current - elapsed;
          idleTimer.current = setTimeout(() => {
            startCountdown(warningSecRef.current);
          }, remainingIdle);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, clearTimers, startCountdown]);

  return { warningVisible, secondsRemaining, resetTimer };
}
