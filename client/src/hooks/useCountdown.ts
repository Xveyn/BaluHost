import { useEffect, useState } from 'react';

export function formatCountdown(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/**
 * Per-second countdown string. Re-anchors to `seconds` whenever it changes
 * (each poll supplies a fresh server value). Returns null when `seconds` is null.
 */
export function useCountdown(seconds: number | null): string | null {
  const [remaining, setRemaining] = useState<number | null>(seconds);

  // Re-anchor on input change.
  useEffect(() => {
    setRemaining(seconds);
  }, [seconds]);

  useEffect(() => {
    if (seconds == null) return;
    const id = setInterval(() => {
      setRemaining((prev) => (prev == null ? null : Math.max(0, prev - 1)));
    }, 1000);
    return () => clearInterval(id);
  }, [seconds]);

  return remaining == null ? null : formatCountdown(remaining);
}
