import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useFileShares } from '../../hooks/useFileShares';
import * as sharesApi from '../../api/shares';
import type { FileShare, SharedWithMe } from '../../api/shares';

vi.mock('../../api/shares');
const api = vi.mocked(sharesApi);

const stats = { total_file_shares: 2, active_file_shares: 1, files_shared_with_me: 3 };

beforeEach(() => {
  vi.clearAllMocks();
  api.listFileShares.mockResolvedValue([{ id: 1 } as unknown as FileShare]);
  api.listFilesSharedWithMe.mockResolvedValue([{ share_id: 9 } as unknown as SharedWithMe]);
  api.getShareStatistics.mockResolvedValue(stats);
});

describe('useFileShares', () => {
  it('exposes all three reads under the SharesPage state names', async () => {
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fileShares).toHaveLength(1);
    expect(result.current.sharedWithMe).toHaveLength(1);
    expect(result.current.statistics).toEqual(stats);
    expect(result.current.error).toBeNull();
  });

  it('stays loading until every query settled', async () => {
    let resolveStats!: (v: typeof stats) => void;
    api.getShareStatistics.mockReturnValue(new Promise((r) => { resolveStats = r; }));
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.fileShares).toHaveLength(1));
    expect(result.current.loading).toBe(true);
    resolveStats(stats);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('surfaces the first failing query as raw error', async () => {
    api.listFileShares.mockRejectedValue(new Error('shares boom'));
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect((result.current.error as Error).message).toBe('shares boom');
    expect(result.current.fileShares).toEqual([]);
  });
});
