import { useEffect, useState } from 'react';
import { getChannelStatus } from '../api/channelStatus';
import type { ChannelStatusResponse } from '../api/channelStatus';

export type Channel = ChannelStatusResponse['channel'];

interface ChannelStatusState {
  channel: Channel;
  isLocal: boolean;
  isLoading: boolean;
}

const FAIL_SAFE: ChannelStatusState = {
  channel: 'remote',
  isLocal: false,
  isLoading: false,
};

// Module-level cache — channel does not change for the lifetime of the session.
let cached: ChannelStatusState | null = null;
let inflight: Promise<ChannelStatusState> | null = null;

async function load(): Promise<ChannelStatusState> {
  if (cached) return cached;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const { channel } = await getChannelStatus();
      cached = { channel, isLocal: channel === 'local', isLoading: false };
    } catch {
      // Fail closed: unknown channel → treat as remote, destructive buttons stay disabled.
      cached = { ...FAIL_SAFE };
    } finally {
      inflight = null;
    }
    return cached!;
  })();
  return inflight;
}

export function useChannelStatus(): ChannelStatusState {
  const [state, setState] = useState<ChannelStatusState>(
    cached ?? { channel: 'remote', isLocal: false, isLoading: true }
  );

  useEffect(() => {
    let alive = true;
    load().then((result) => {
      if (alive) setState(result);
    });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}

// For tests — reset the module cache between cases.
export function __resetChannelStatusCache(): void {
  cached = null;
  inflight = null;
}
