import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createTestQueryClient, createQueryWrapper } from '../helpers/queryClient';
import { queryKeys } from '../../lib/queryKeys';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/gpuPower', () => ({
  gpuPowerApi: {
    getStatus: vi.fn(),
    getConfig: vi.fn(),
    getCapabilities: vi.fn(),
    putConfig: vi.fn(),
  },
}));

import { gpuPowerApi } from '../../api/gpuPower';
import { useGpuPower } from '../../hooks/useGpuPower';

const api = gpuPowerApi as unknown as {
  getStatus: ReturnType<typeof vi.fn>;
  getConfig: ReturnType<typeof vi.fn>;
  getCapabilities: ReturnType<typeof vi.fn>;
  putConfig: ReturnType<typeof vi.fn>;
};

const cfg = (enabled: boolean) => ({ enabled }) as never;

beforeEach(() => {
  vi.clearAllMocks();
  api.getStatus.mockResolvedValue({ detected: true, current_state: 'active' } as never);
  api.getCapabilities.mockResolvedValue({} as never);
});

describe('useGpuPower', () => {
  it('seeds the draft from the loaded config', async () => {
    api.getConfig.mockResolvedValue(cfg(true));
    const { result } = renderHook(() => useGpuPower(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.draft).toEqual({ enabled: true }));
    expect(result.current.dirty).toBe(false);
  });

  it('marks dirty once the draft diverges from config', async () => {
    api.getConfig.mockResolvedValue(cfg(true));
    const { result } = renderHook(() => useGpuPower(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.draft).toEqual({ enabled: true }));

    act(() => result.current.setDraft({ enabled: false } as never));
    expect(result.current.dirty).toBe(true);
  });

  it('does NOT clobber an in-progress draft edit on the next poll (draft-guard)', async () => {
    api.getConfig.mockResolvedValue(cfg(true));
    const client = createTestQueryClient();
    const { result } = renderHook(() => useGpuPower(), { wrapper: createQueryWrapper(client) });
    await waitFor(() => expect(result.current.draft).toEqual({ enabled: true }));

    // User edits the draft.
    act(() => result.current.setDraft({ enabled: false } as never));

    // A poll returns a different server config.
    api.getConfig.mockResolvedValue(cfg(false));
    await act(async () => {
      await client.invalidateQueries({ queryKey: queryKeys.gpuPower.overview() });
    });

    // config reflects the server, but the user's draft edit survives.
    await waitFor(() => expect(result.current.config).toEqual({ enabled: false }));
    expect(result.current.draft).toEqual({ enabled: false });
    // (draft happened to equal the new config here only because the user set the
    // same value — assert the edit was never reset by re-checking dirty logic in
    // the divergent case below.)
  });

  it('keeps a divergent draft when the poll brings an unrelated config change', async () => {
    api.getConfig.mockResolvedValue(cfg(true));
    const client = createTestQueryClient();
    const { result } = renderHook(() => useGpuPower(), { wrapper: createQueryWrapper(client) });
    await waitFor(() => expect(result.current.draft).toEqual({ enabled: true }));

    // Draft edited to a NEW object the server will never send this round.
    act(() => result.current.setDraft({ enabled: true, edited: 1 } as never));

    api.getConfig.mockResolvedValue(cfg(false));
    await act(async () => {
      await client.invalidateQueries({ queryKey: queryKeys.gpuPower.overview() });
    });

    await waitFor(() => expect(result.current.config).toEqual({ enabled: false }));
    // Draft must NOT have been reset to the polled config.
    expect(result.current.draft).toEqual({ enabled: true, edited: 1 });
    expect(result.current.dirty).toBe(true);
  });

  it('saves the draft, clears dirty, and re-seeds from the saved config', async () => {
    api.getConfig.mockResolvedValue(cfg(true));
    api.putConfig.mockResolvedValue(cfg(false));
    const { result } = renderHook(() => useGpuPower(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.draft).toEqual({ enabled: true }));

    act(() => result.current.setDraft({ enabled: false } as never));
    await act(async () => {
      await result.current.save();
    });

    expect(api.putConfig).toHaveBeenCalledWith({ enabled: false });
    expect(result.current.config).toEqual({ enabled: false });
    expect(result.current.draft).toEqual({ enabled: false });
    expect(result.current.dirty).toBe(false);
  });
});
