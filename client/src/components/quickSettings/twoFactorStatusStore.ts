/**
 * Lazy module-level cache for the user's 2FA status.
 *
 * Same pattern as lib/byteUnits.ts — module state, no React Context.
 * Loaded on first access, kept for the duration of the page load,
 * invalidated explicitly via refreshStatus() after a successful setup.
 */
import { useEffect, useState } from 'react';
import { get2FAStatus, type TwoFactorStatus } from '../../api/two-factor';

let cached: TwoFactorStatus | null = null;
let inflight: Promise<TwoFactorStatus | null> | null = null;

export async function loadStatusOnce(): Promise<TwoFactorStatus | null> {
  if (cached) return cached;
  if (inflight) return inflight;
  inflight = get2FAStatus()
    .then((s) => {
      cached = s;
      return s as TwoFactorStatus | null;
    })
    .catch(() => null)
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function refreshStatus(): void {
  cached = null;
  inflight = null;
}

/**
 * React hook that triggers `loadStatusOnce()` when `enabled` is true.
 * Returns the cached status, or null while loading or on error.
 */
export function useTwoFactorStatus(enabled: boolean): TwoFactorStatus | null {
  const [status, setStatus] = useState<TwoFactorStatus | null>(cached);

  useEffect(() => {
    if (!enabled) return;
    if (cached) {
      setStatus(cached);
      return;
    }
    let cancelled = false;
    void loadStatusOnce().then((s) => {
      if (!cancelled) setStatus(s);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return status;
}
