import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { FileItem } from '../../components/file-manager/types';

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock('../../api/vcl', () => ({
  vclApi: { getUserQuota: vi.fn(), getFileVersions: vi.fn() },
  getTrackingRules: vi.fn(),
  addTrackingRule: vi.fn(),
  removeTrackingRule: vi.fn(),
  checkFileTracking: vi.fn(),
}));
vi.mock('../../api/files', () => ({ getUserRootUsage: vi.fn() }));

import { vclApi, getTrackingRules, addTrackingRule, checkFileTracking } from '../../api/vcl';
import { getUserRootUsage } from '../../api/files';
import { useVclFileInfo } from '../../hooks/useVclFileInfo';

const file = (over: Partial<FileItem>): FileItem => ({ name: 'x', path: 'x', size: 0, type: 'file', modifiedAt: 't', ...over });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(vclApi.getUserQuota).mockResolvedValue({ usage_percent: 82, current_usage_bytes: 82, max_size_bytes: 100 } as never);
  vi.mocked(getUserRootUsage).mockResolvedValue({ user_root_used_bytes: 500 } as never);
  vi.mocked(vclApi.getFileVersions).mockResolvedValue({ total: 3 } as never);
  vi.mocked(getTrackingRules).mockResolvedValue({ mode: 'manual', rules: [] } as never);
  vi.mocked(checkFileTracking).mockResolvedValue({ is_tracked: true } as never);
  vi.mocked(addTrackingRule).mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe('useVclFileInfo', () => {
  it('maps quota to vclQuota with a warning level and exposes user-root usage', async () => {
    const { result } = renderHook(() => useVclFileInfo([]), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.vclQuota).not.toBeNull());
    expect(result.current.vclQuota).toEqual({ usagePercent: 82, warning: 'warning', current: 82, max: 100 });
    await waitFor(() => expect(result.current.userRootUsageBytes).toBe(500));
  });

  it('loads version counts for files with a file_id (fan-out)', async () => {
    const files = [file({ file_id: 11 }), file({ file_id: 22 })];
    const { result } = renderHook(() => useVclFileInfo(files), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.versionCounts[11]).toBe(3));
    expect(vclApi.getFileVersions).toHaveBeenCalledWith(11);
    expect(result.current.versionCounts[22]).toBe(3);
  });

  it('toggleTracking (manual mode, currently tracked) flips status', async () => {
    const f = file({ file_id: 11, name: 'doc' });
    const filesArr = [f];
    const { result } = renderHook(() => useVclFileInfo(filesArr), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.trackingStatus[11]).toBe(true));
    await act(async () => { await result.current.toggleTracking(f); });
    expect(result.current.trackingStatus[11]).toBe(false);
  });
});
