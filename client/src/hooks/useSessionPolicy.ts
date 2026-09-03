/**
 * Reads the admin-configured session limits once per login.
 *
 * The idle logout used to be hardcoded at 4 min + 60 s. Those values now live
 * in the `auth_policy` singleton and are served by `GET /api/auth/session-policy`.
 * Until the answer arrives — and permanently if it never does — the hook
 * reports the old hardcoded values: a failed read must not silently switch the
 * idle logout off.
 */
import { useEffect, useState } from 'react';
import { getSessionPolicy } from '../api/pin';
import { DEFAULT_IDLE_MS, DEFAULT_WARNING_SEC } from '../lib/sessionDefaults';

export interface SessionPolicyValues {
  idleMs: number;
  warningSec: number;
  /** False when the admin set the idle timeout to 0 (no automatic logout). */
  idleEnabled: boolean;
}

const FALLBACK: SessionPolicyValues = {
  idleMs: DEFAULT_IDLE_MS,
  warningSec: DEFAULT_WARNING_SEC,
  idleEnabled: true,
};

export function useSessionPolicy(enabled: boolean): SessionPolicyValues {
  const [values, setValues] = useState<SessionPolicyValues>(FALLBACK);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    getSessionPolicy()
      .then((policy) => {
        if (cancelled) return;
        setValues({
          idleMs: policy.idle_timeout_minutes * 60 * 1000,
          warningSec: policy.idle_warning_seconds,
          idleEnabled: policy.idle_timeout_minutes > 0,
        });
      })
      .catch(() => {
        // Keep the fallbacks. Never disable the idle logout on an error.
      });

    return () => { cancelled = true; };
  }, [enabled]);

  return values;
}
