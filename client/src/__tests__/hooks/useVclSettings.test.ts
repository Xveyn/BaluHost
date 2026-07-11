import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const { overview, users, storage } = vi.hoisted(() => ({
  overview: {
    total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
    unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
    total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
    total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null,
  },
  users: [{ user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500, usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic' as const }],
  storage: null,
}));

vi.mock('../../api/vcl', () => ({
  getAdminOverview: vi.fn().mockResolvedValue(overview),
  getAdminUsers: vi.fn().mockResolvedValue({ users, total: 1 }),
  getStorageInfo: vi.fn().mockResolvedValue(storage),
  updateUserSettingsAdmin: vi.fn().mockResolvedValue({}),
  triggerCleanup: vi.fn().mockResolvedValue({ deleted_versions: 0, freed_bytes: 0 }),
  getReconciliationPreview: vi.fn().mockResolvedValue({ total_mismatches: 0, mismatches: [], affected_users: [] }),
  applyReconciliation: vi.fn().mockResolvedValue({ message: 'ok' }),
  formatBytes: (n: number) => `${n}B`,
}));
vi.mock('../../lib/errorHandling', () => ({ getApiErrorMessage: (_e: unknown, fb: string) => fb }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { useVclSettings } from '../../hooks/useVclSettings';
import * as api from '../../api/vcl';

describe('useVclSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('loads overview + users on mount', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    expect(result.current.users).toHaveLength(1);
    expect(api.getStorageInfo).toHaveBeenCalled();
  });

  it('does not call triggerCleanup when the confirm is declined (non-dry-run)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    await act(async () => { await result.current.handleCleanup(false); });
    expect(api.triggerCleanup).not.toHaveBeenCalled();
  });

  it('sets the no-mismatches success message when the scan finds none', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    await act(async () => { await result.current.handleScanMismatches(); });
    expect(result.current.successMessage).toBe('No ownership mismatches found');
  });

  it('handleSaveUserSettings sends the edit form for the editing user', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    act(() => result.current.handleEditUser(users[0]));
    await act(async () => { await result.current.handleSaveUserSettings(); });
    expect(api.updateUserSettingsAdmin).toHaveBeenCalledWith(
      1, expect.objectContaining({ max_size_bytes: 1000, is_enabled: true }),
    );
  });
});
