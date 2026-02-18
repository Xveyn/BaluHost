/**
 * Hook for fetching activity feed from audit logs
 */
import { useState, useEffect, useCallback } from 'react';
import { loggingApi, type FileAccessLog } from '../api/logging';
import { formatNumber } from '../lib/formatters';

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
  days?: number;
  refreshInterval?: number;
}

interface UseActivityFeedReturn {
  activities: ActivityItem[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// Map action to icon
export function getActionIcon(action: string): string {
  switch (action.toLowerCase()) {
    case 'upload':
      return 'upload';
    case 'download':
      return 'download';
    case 'delete':
      return 'delete';
    case 'create':
    case 'mkdir':
      return 'create';
    case 'login':
    case 'auth':
      return 'user';
    case 'move':
    case 'rename':
      return 'move';
    case 'copy':
      return 'copy';
    case 'share':
      return 'share';
    default:
      return 'file';
  }
}

// Map action to human-readable title
export function getActionTitle(action: string): string {
  switch (action.toLowerCase()) {
    case 'upload':
      return 'File Uploaded';
    case 'download':
      return 'File Downloaded';
    case 'delete':
      return 'File Deleted';
    case 'create':
    case 'mkdir':
      return 'Created';
    case 'login':
      return 'User Login';
    case 'auth':
      return 'Authentication';
    case 'move':
      return 'File Moved';
    case 'rename':
      return 'File Renamed';
    case 'copy':
      return 'File Copied';
    case 'share':
      return 'File Shared';
    default:
      return action.charAt(0).toUpperCase() + action.slice(1);
  }
}

// Format relative time
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return 'just now';
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  }
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  }
  if (diffDays < 7) {
    return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  }
  return date.toLocaleDateString();
}

// Transform log to activity item
export function transformLog(log: FileAccessLog, index: number): ActivityItem {
  const timestamp = new Date(log.timestamp);
  const resourcePath = log.resource || '';
  const fileName = resourcePath.split('/').pop() || resourcePath;

  let detail = fileName || log.resource;
  if (log.user && log.user !== 'unknown') {
    detail = `${log.user} • ${detail}`;
  }
  if (log.details?.size_bytes) {
    const sizeKb = formatNumber(log.details.size_bytes / 1024, 1);
    detail += ` (${sizeKb} KB)`;
  }

  return {
    id: `${log.timestamp}-${index}`,
    title: getActionTitle(log.action),
    detail,
    ago: formatRelativeTime(timestamp),
    icon: getActionIcon(log.action),
    timestamp,
    success: log.success,
  };
}

export function useActivityFeed(options: UseActivityFeedOptions = {}): UseActivityFeedReturn {
  const { limit = 5, days = 1, refreshInterval = 30000 } = options;

  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const response = await loggingApi.getFileAccessLogs({ limit, days });
      const items = response.logs.map((log, idx) => transformLog(log, idx));
      setActivities(items);
      setError(null);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || (err instanceof Error ? err.message : 'Failed to load activity feed'));
    }
  }, [limit, days]);

  // Initial load
  useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [loadData]);

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, loadData]);

  return {
    activities,
    loading,
    error,
    refetch: loadData,
  };
}
