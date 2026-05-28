import { useEffect, useRef, useState } from 'react';
import { getStatusBarState, StatusBarStateResponse } from '../api/statusBar';

const POLL_MS = 10_000;
const MAX_FAILURES = 3;

export interface UseStatusBarState {
  state: StatusBarStateResponse | null;
  stale: boolean;
}

export function useStatusBarState(): UseStatusBarState {
  const [state, setState] = useState<StatusBarStateResponse | null>(null);
  const [stale, setStale] = useState(false);
  const failuresRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      if (document.hidden) return; // pause when tab not visible
      try {
        const data = await getStatusBarState();
        if (cancelled) return;
        failuresRef.current = 0;
        setState(data);
        setStale(false);
      } catch {
        if (cancelled) return;
        failuresRef.current += 1;
        if (failuresRef.current >= MAX_FAILURES) {
          setState(null);
        } else {
          setStale(true); // keep last-known state, flag stale
        }
      }
    }

    poll(); // initial fetch
    const id = setInterval(poll, POLL_MS);
    const onVisible = () => { if (!document.hidden) poll(); };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return { state, stale };
}
