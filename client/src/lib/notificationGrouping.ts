/**
 * Client-side notification grouping for the dropdown.
 *
 * Groups notifications with the same category + type that arrived within
 * a configurable time window (default 60 min).
 */
import type { Notification } from '../api/notifications';

const GROUP_WINDOW_MS = 60 * 60 * 1000; // 60 minutes

export interface NotificationGroup {
  /** Representative notification (most recent in group) */
  latest: Notification;
  /** All notifications in this group */
  items: Notification[];
  /** Number of items in the group */
  count: number;
  /** Grouping key (category:type) */
  key: string;
}

/**
 * Group a list of notifications by category + type within a time window.
 * Notifications that don't match any group stay as single-item groups.
 */
export function groupNotifications(notifications: Notification[]): NotificationGroup[] {
  if (notifications.length === 0) return [];

  const groups: NotificationGroup[] = [];
  const used = new Set<number>();

  // Sort by created_at descending (newest first) - should already be sorted
  const sorted = [...notifications].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  for (let i = 0; i < sorted.length; i++) {
    if (used.has(sorted[i].id)) continue;

    const current = sorted[i];
    const groupKey = `${current.category}:${current.notification_type}`;
    const currentTime = new Date(current.created_at).getTime();
    const items: Notification[] = [current];
    used.add(current.id);

    // Find similar notifications within the time window
    for (let j = i + 1; j < sorted.length; j++) {
      if (used.has(sorted[j].id)) continue;
      const candidate = sorted[j];
      const candidateKey = `${candidate.category}:${candidate.notification_type}`;
      const candidateTime = new Date(candidate.created_at).getTime();

      if (candidateKey === groupKey && currentTime - candidateTime <= GROUP_WINDOW_MS) {
        items.push(candidate);
        used.add(candidate.id);
      }
    }

    groups.push({
      latest: current,
      items,
      count: items.length,
      key: `${groupKey}:${current.id}`,
    });
  }

  return groups;
}
