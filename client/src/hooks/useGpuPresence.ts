import { useEffect, useState } from 'react';
import { getGpuInfo } from '../api/monitoring';
import type { GpuDeviceInfo } from '../api/monitoring';

interface GpuPresence {
  present: boolean;
  info: GpuDeviceInfo | null;
  loading: boolean;
}

// Module-level cache — GPU detection does not change at runtime.
let cached: GpuPresence | null = null;
let inflight: Promise<GpuPresence> | null = null;

async function load(): Promise<GpuPresence> {
  if (cached) return cached;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const info = await getGpuInfo();
      cached = { present: info !== null, info, loading: false };
    } catch {
      cached = { present: false, info: null, loading: false };
    } finally {
      inflight = null;
    }
    return cached!;
  })();
  return inflight;
}

export function useGpuPresence(): GpuPresence {
  const [state, setState] = useState<GpuPresence>(
    cached ?? { present: false, info: null, loading: true }
  );

  useEffect(() => {
    let alive = true;
    load().then((result) => {
      if (alive) setState(result);
    });
    return () => { alive = false; };
  }, []);

  return state;
}

// For tests — reset the module cache between cases.
export function __resetGpuPresenceCache() {
  cached = null;
  inflight = null;
}
