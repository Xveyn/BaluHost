import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useBackups } from '../../hooks/useBackups';
import * as backupApi from '../../api/backup';

vi.mock('../../api/backup');
const api = vi.mocked(backupApi);

const sample = {
  backups: [
    {
      id: 1, filename: 'b1.tar.gz', filepath: '/tmp/b1.tar.gz', size_bytes: 1000,
      size_mb: 0, backup_type: 'full' as const, status: 'completed' as const,
      created_at: '2026-07-01T00:00:00Z', completed_at: null, creator_id: 1,
      error_message: null, includes_database: true, includes_files: true, includes_config: false,
    },
  ],
  total_size_bytes: 1000,
  total_size_mb: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useBackups', () => {
  it('unwraps the backup list from the response', async () => {
    api.listBackups.mockResolvedValue(sample);
    const { result } = renderHook(() => useBackups(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.backups).toHaveLength(1);
    expect(result.current.backups[0].filename).toBe('b1.tar.gz');
    expect(result.current.error).toBeNull();
  });

  it('exposes the raw error when the fetch rejects', async () => {
    api.listBackups.mockRejectedValue(new Error('backup boom'));
    const { result } = renderHook(() => useBackups(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect((result.current.error as Error).message).toBe('backup boom');
    expect(result.current.backups).toEqual([]);
  });
});
