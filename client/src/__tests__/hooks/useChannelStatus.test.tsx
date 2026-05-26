import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import * as api from '../../api/channelStatus';
import { useChannelStatus, __resetChannelStatusCache } from '../../hooks/useChannelStatus';

vi.mock('../../api/channelStatus');

describe('useChannelStatus', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    __resetChannelStatusCache();
  });

  it('returns isLocal=true when API says local', async () => {
    (api.getChannelStatus as any).mockResolvedValue({ channel: 'local' });
    const { result } = renderHook(() => useChannelStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isLocal).toBe(true);
    expect(result.current.channel).toBe('local');
  });

  it('returns isLocal=false when API says remote', async () => {
    (api.getChannelStatus as any).mockResolvedValue({ channel: 'remote' });
    const { result } = renderHook(() => useChannelStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isLocal).toBe(false);
    expect(result.current.channel).toBe('remote');
  });

  it('defaults to remote (fail-safe) while loading', () => {
    (api.getChannelStatus as any).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useChannelStatus());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isLocal).toBe(false);
    expect(result.current.channel).toBe('remote');
  });

  it('fails closed (channel=remote) when API throws', async () => {
    (api.getChannelStatus as any).mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useChannelStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.channel).toBe('remote');
    expect(result.current.isLocal).toBe(false);
  });
});
