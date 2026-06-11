/**
 * Presence heartbeat (issue #214).
 *
 * Sends POST /api/system/sleep/presence on an interval so the backend knows
 * a user is actively present and will not auto-escalate to true suspend.
 *
 * Mode is learned from the heartbeat response:
 * - 'active'  (default): beats only while the tab is visible — a forgotten
 *   background tab does not keep the server awake.
 * - 'session': beats while the tab is open, regardless of visibility.
 *
 * Best-effort by design: all errors are swallowed; the hook must never
 * disturb the UI. Mount it once in the authenticated layout — unmounting
 * (logout) stops the heartbeat.
 */
import { useEffect } from 'react';
import { sendPresenceHeartbeat, type PresenceMode } from '../api/sleep';

const DEFAULT_INTERVAL_MS = 45_000;
const CLIENT_ID_KEY = 'baluhost_presence_client_id';

function getClientId(): string {
  let id = sessionStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export function usePresenceHeartbeat(): void {
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let intervalMs = DEFAULT_INTERVAL_MS;
    let mode: PresenceMode = 'active';
    const clientId = getClientId();

    const beat = async () => {
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
  }, []);
}
