/**
 * Presence heartbeat (issue #214, idle-pause #222).
 *
 * Sends POST /api/system/sleep/presence on an interval so the backend knows
 * a user is actively present and will not auto-escalate to true suspend.
 *
 * Mode is learned from the heartbeat response:
 * - 'active'  (default): beats only while the tab is visible — a forgotten
 *   background tab does not keep the server awake.
 * - 'session': beats while the tab is open, regardless of visibility.
 *
 * Options:
 * - `paused`  — when true, no beats are sent (e.g. the idle-logout warning is
 *   showing: the user has been inactive ≥4 min, so the tab must stop signalling
 *   presence). Changes often, so it is read through a ref and never tears down
 *   the interval.
 * - `enabled` — when false, the heartbeat is fully off (e.g. no user logged in).
 *
 * Best-effort by design: all errors are swallowed; the hook must never
 * disturb the UI. Mount it once at the authenticated app root (AppRoutes),
 * gated on auth via `enabled` — unmounting/disabling stops the heartbeat.
 */
import { useEffect, useRef } from 'react';
import { sendPresenceHeartbeat, type PresenceMode } from '../api/sleep';

const DEFAULT_INTERVAL_MS = 45_000;
const CLIENT_ID_KEY = 'baluhost_presence_client_id';

interface UsePresenceHeartbeatOptions {
  /** When true, skip sending heartbeats (idle-logout warning visible). */
  paused?: boolean;
  /** When false, the heartbeat is fully disabled (no user logged in). */
  enabled?: boolean;
}

function getClientId(): string {
  let id = sessionStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export function usePresenceHeartbeat(options: UsePresenceHeartbeatOptions = {}): void {
  const { paused = false, enabled = true } = options;

  // `paused` flips on every idle warning; keep it in a ref so toggling it does
  // not re-run the effect (which would tear down and recreate the interval).
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    if (!enabled) return;

    let timer: ReturnType<typeof setInterval> | null = null;
    let intervalMs = DEFAULT_INTERVAL_MS;
    let mode: PresenceMode = 'active';
    const clientId = getClientId();

    const beat = async () => {
      if (pausedRef.current) return;
      if (mode === 'active' && document.visibilityState !== 'visible') return;
      try {
        const res = await sendPresenceHeartbeat({ client_id: clientId, client_type: 'web' });
        mode = res.mode;
        const nextMs = Math.max(15, res.heartbeat_interval_seconds) * 1000;
        if (nextMs !== intervalMs) {
          intervalMs = nextMs;
          schedule();
        }
      } catch {
        // best-effort: never disturb the UI
      }
    };

    const schedule = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(() => { void beat(); }, intervalMs);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void beat();
    };

    void beat();
    schedule();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [enabled]);
}
