import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/cloud-export', () => ({
  listCloudExports: vi.fn(),
  getCloudExportStatistics: vi.fn(),
  revokeCloudExport: vi.fn(),
  retryCloudExport: vi.fn(),
}));

import toast from 'react-hot-toast';
import { listCloudExports, getCloudExportStatistics, revokeCloudExport, retryCloudExport } from '../../api/cloud-export';
import { useCloudExports } from '../../hooks/useCloudExports';

beforeEach(() => {
  vi.clearAllMocks();
  (listCloudExports as any).mockResolvedValue([{ id: 1, status: 'ready' }]);
  (getCloudExportStatistics as any).mockResolvedValue({ active_exports: 1, total_exports: 1, total_upload_bytes: 0 });
});

describe('useCloudExports', () => {
  it('loads exports + stats on mount', async () => {
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.cloudExports).toHaveLength(1);
    expect(result.current.cloudStats?.active_exports).toBe(1);
  });

  it('revoke calls the API, reloads and toasts success', async () => {
    (revokeCloudExport as any).mockResolvedValue(undefined);
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.revoke(1); });
    expect(revokeCloudExport).toHaveBeenCalledWith(1);
    expect(listCloudExports).toHaveBeenCalledTimes(2); // mount + reload
    expect(toast.success).toHaveBeenCalled();
  });

  it('retry toasts error when the API rejects', async () => {
    (retryCloudExport as any).mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useCloudExports());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.retry(1); });
    expect(toast.error).toHaveBeenCalled();
  });
});
