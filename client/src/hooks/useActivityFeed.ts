/**
 * Hook for fetching the dashboard activity feed from the user-scoped
 * /api/activity API. Admins may request all users' activity (scope=all).
 */
import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getRecentActivities, type ActivityItem as ApiActivityItem } from '../api/activity';
import { queryKeys } from '../lib/queryKeys';
import { formatBytes } from '../lib/formatters';
import { getApiErrorMessage } from '../lib/errorHandling';

export interface ActivityItem {
  id: string;
  title: string;
  detail: string;
  ago: string;
  icon: string;
  timestamp: Date;
  success: boolean;
}

interface UseActivityFeedOptions {
  limit?: number;
  allUsers?: boolean;
  refreshInterval?: number;
}

interface UseActivityFeedReturn {
  activities: ActivityItem[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// Map a dotted action_type (e.g. "file.upload", "folder.create") to an icon key
// understood by ActivityFeed's ActivityIcon and to an i18n title sub-key.
const ACTION_MAP: Record<string, { icon: string; titleKey: string }> = {
  'file.upload': { icon: 'upload', titleKey: 'upload' },
  'file.download': { icon: 'download', titleKey: 'download' },
  'file.delete': { icon: 'delete', titleKey: 'delete' },
  'file.edit': { icon: 'file', titleKey: 'edit' },
  'file.open': { icon: 'file', titleKey: 'open' },
  'file.move': { icon: 'move', titleKey: 'move' },
  'file.rename': { icon: 'move', titleKey: 'rename' },
  'file.share': { icon: 'share', titleKey: 'share' },
  'file.permission': { icon: 'share', titleKey: 'permission' },
  'folder.create': { icon: 'create', titleKey: 'create' },
  'sync.triggered': { icon: 'file', titleKey: 'sync' },
};

export function mapActionType(actionType: string): { icon: string; titleKey: string } {
  return ACTION_MAP[actionType] ?? { icon: 'file', titleKey: 'default' };
}

// Format relative time
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return date.toLocaleDateString();
}

export function useActivityFeed(options: UseActivityFeedOptions = {}): UseActivityFeedReturn {
  const { limit = 5, allUsers = false, refreshInterval = 30000 } = options;
  const { t } = useTranslation('dashboard');

  const scope: 'mine' | 'all' = allUsers ? 'all' : 'mine';

  // Query holds the raw API items (JSON-serializable → persister-friendly); the
  // view mapping (i18n titles, relative "ago") is derived per render below. The
  // feed is user-scoped — AuthContext clears the query cache on every identity
  // change, so entries can't leak between users.
  const query = useQuery({
    queryKey: queryKeys.activity.recent(scope, limit),
    queryFn: async () => (await getRecentActivities({ limit, scope })).activities,
    refetchInterval: refreshInterval > 0 ? refreshInterval : false,
  });

  const toViewItem = useCallback(
    (item: ApiActivityItem): ActivityItem => {
      const { icon, titleKey } = mapActionType(item.action_type);
      const timestamp = new Date(item.created_at);

      let detail = item.file_name;
      if (item.username) detail = `${item.username} • ${detail}`;
      if (item.file_size != null) detail += ` (${formatBytes(item.file_size)})`;

      return {
        id: String(item.id),
        title: t(`activity.actions.${titleKey}`),
        detail,
        ago: formatRelativeTime(timestamp),
        icon,
        timestamp,
        // The activity API records only successful operations, so this is
        // always true (the failure-state styling in ActivityFeed is unused here).
        success: true,
      };
    },
    [t],
  );

  const activities = useMemo(
    () => (query.data ?? []).map(toViewItem),
    [query.data, toViewItem],
  );

  return {
    activities,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load activity feed') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}
