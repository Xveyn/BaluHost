import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { SSDCacheStats, SSDCacheConfigResponse, CacheHealthResponse } from '../../api/ssd-file-cache';

vi.mock('../../api/raid', () => ({
  getRaidStatus: vi.fn().mockResolvedValue({ arrays: [{ name: 'md0' }] }),
}));
const mockConfirm = vi.fn();
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm, dialog: null }),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../lib/errorHandling', () => ({
  getApiErrorMessage: (_e: unknown, fb: string) => fb,
  handleApiError: vi.fn(),
}));

// vi.mock factories are hoisted above ordinary top-level `const`s, so the
// shared fixtures below must go through vi.hoisted() (same pattern as
// useFileUpload.test.tsx) or the ssd-file-cache mock factory below hits a
// TDZ ReferenceError on `stats`/`config`/`health`.
const { stats, config, health } = vi.hoisted(() => {
  const stats: SSDCacheStats = {
    array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1000,
    current_size_bytes: 500, usage_percent: 50, total_entries: 3, valid_entries: 3,
    total_hits: 10, total_misses: 2, hit_rate_percent: 83.3, total_bytes_served: 999,
    ssd_available_bytes: 800, ssd_total_bytes: 1000,
  };
  const config: SSDCacheConfigResponse = {
    array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1000,
    current_size_bytes: 500, eviction_policy: 'lfru', min_file_size_bytes: 1,
    max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 10,
    total_misses: 2, total_bytes_served_from_cache: 999, updated_at: null,
  };
  const health: CacheHealthResponse = {
    array_name: 'md0', is_mounted: true, ssd_total_bytes: 1000,
    ssd_available_bytes: 800, ssd_used_percent: 20, cache_dir_exists: true,
  };
  return { stats, config, health };
});

vi.mock('../../api/ssd-file-cache', () => ({
  getCacheStats: vi.fn().mockResolvedValue(stats),
  getCacheConfig: vi.fn().mockResolvedValue(config),
  getCacheHealth: vi.fn().mockResolvedValue(health),
  getCacheEntries: vi.fn().mockResolvedValue({ entries: [], total: 0 }),
  updateCacheConfig: vi.fn().mockResolvedValue(config),
  evictEntry: vi.fn().mockResolvedValue({ freed_bytes: 10, source_path: '/x' }),
  triggerEviction: vi.fn().mockResolvedValue({ freed_bytes: 10, deleted_count: 1 }),
  clearCache: vi.fn().mockResolvedValue({ freed_bytes: 10, deleted_count: 1 }),
}));

import { useSsdFileCache } from '../../hooks/useSsdFileCache';
import * as api from '../../api/ssd-file-cache';

describe('useSsdFileCache', () => {
  beforeEach(() => vi.clearAllMocks());

  it('auto-selects the sole array on mount and loads its data', async () => {
    const { result } = renderHook(() => useSsdFileCache());
    await waitFor(() => expect(result.current.selectedArray).toBe('md0'));
    await waitFor(() => expect(result.current.stats).not.toBeNull());
    expect(result.current.config).not.toBeNull();
  });

  it('does not call clearCache when the confirm dialog is declined', async () => {
    mockConfirm.mockResolvedValueOnce(false);
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.selectedArray).toBe('md0'));
    await act(async () => { await result.current.handleClearCache(); });
    expect(api.clearCache).not.toHaveBeenCalled();
  });

  it('handleConfigChange marks the form dirty and updates the field', async () => {
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => result.current.handleConfigChange('is_enabled', false));
    expect(result.current.configDirty).toBe(true);
    expect(result.current.configForm.is_enabled).toBe(false);
  });

  it('handleSaveConfig sends the current form to updateCacheConfig', async () => {
    const { result } = renderHook(() => useSsdFileCache('md0'));
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => result.current.handleConfigChange('max_size_bytes', 2048));
    await act(async () => { await result.current.handleSaveConfig(); });
    expect(api.updateCacheConfig).toHaveBeenCalledWith(
      'md0', expect.objectContaining({ max_size_bytes: 2048 }),
    );
  });
});
