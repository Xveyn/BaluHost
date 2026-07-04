import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useActivityFeed } from '../../hooks/useActivityFeed';
import type { ActivityListResponse } from '../../api/activity';

const tFn = (key: string) => key;
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tFn }),
}));

vi.mock('../../lib/errorHandling', () => ({
  getApiErrorMessage: (_e: unknown, fallback: string) => fallback,
}));

vi.mock('../../lib/formatters', () => ({
  formatBytes: (n: number) => `${n} B`,
}));

vi.mock('../../api/activity', () => ({
  getRecentActivities: vi.fn(),
}));

import { getRecentActivities } from '../../api/activity';

const adminResponse: ActivityListResponse = {
  total: 2,
  has_more: false,
  activities: [
    {
      id: 1, user_id: 5, username: 'alice', action_type: 'file.upload',
      file_path: 'alice/report.pdf', file_name: 'report.pdf', is_directory: false,
      file_size: 2048, mime_type: 'application/pdf', source: 'server',
      device_id: null, metadata: null, created_at: new Date().toISOString(),
    },
    {
      id: 2, user_id: 6, username: 'bob', action_type: 'folder.create',
      file_path: 'bob/photos', file_name: 'photos', is_directory: true,
      file_size: null, mime_type: null, source: 'server',
      device_id: null, metadata: null, created_at: new Date().toISOString(),
    },
  ],
};

describe('useActivityFeed', () => {
  beforeEach(() => {
    vi.mocked(getRecentActivities).mockResolvedValue(adminResponse);
  });
  afterEach(() => vi.restoreAllMocks());

  it('requests scope=all when allUsers is true and maps action types', async () => {
    const { result } = renderHook(() => useActivityFeed({ limit: 5, allUsers: true }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getRecentActivities).toHaveBeenCalledWith({ limit: 5, scope: 'all' });
    expect(result.current.activities).toHaveLength(2);
    expect(result.current.activities[0].icon).toBe('upload');
    expect(result.current.activities[1].icon).toBe('create');
    expect(result.current.activities[0].title).toBe('activity.actions.upload');
    expect(result.current.activities[1].title).toBe('activity.actions.create');
    expect(result.current.activities[0].detail).toContain('alice');
  });

  it('requests scope=mine when allUsers is false and omits username in detail', async () => {
    vi.mocked(getRecentActivities).mockResolvedValue({
      total: 1, has_more: false,
      activities: [{
        id: 9, user_id: 5, username: null, action_type: 'file.download',
        file_path: 'me/a.txt', file_name: 'a.txt', is_directory: false,
        file_size: null, mime_type: null, source: 'server',
        device_id: null, metadata: null, created_at: new Date().toISOString(),
      }],
    });

    const { result } = renderHook(() => useActivityFeed({ limit: 5 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getRecentActivities).toHaveBeenCalledWith({ limit: 5, scope: 'mine' });
    expect(result.current.activities[0].icon).toBe('download');
    expect(result.current.activities[0].detail).toBe('a.txt');
  });

  it('sets error and leaves activities empty when the request fails', async () => {
    vi.mocked(getRecentActivities).mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useActivityFeed({ limit: 5 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to load activity feed');
    expect(result.current.activities).toEqual([]);
  });
});
