import { describe, it, expect } from 'vitest';
import { groupNotifications } from '../../lib/notificationGrouping';
import type { Notification } from '../../api/notifications';

function makeNotification(overrides: Partial<Notification> & { id: number; created_at: string }): Notification {
  return {
    category: 'system',
    notification_type: 'info',
    title: 'Test',
    message: 'Test message',
    is_read: false,
    user_id: 1,
    ...overrides,
  } as Notification;
}

describe('groupNotifications', () => {
  it('returns empty array for empty input', () => {
    expect(groupNotifications([])).toEqual([]);
  });

  it('returns single-item group for one notification', () => {
    const n = makeNotification({ id: 1, created_at: '2026-01-01T12:00:00Z' });
    const groups = groupNotifications([n]);

    expect(groups).toHaveLength(1);
    expect(groups[0].count).toBe(1);
    expect(groups[0].latest).toBe(n);
  });

  it('groups notifications with same category+type within time window', () => {
    const n1 = makeNotification({ id: 1, created_at: '2026-01-01T12:00:00Z', category: 'system', notification_type: 'backup' });
    const n2 = makeNotification({ id: 2, created_at: '2026-01-01T12:30:00Z', category: 'system', notification_type: 'backup' });

    const groups = groupNotifications([n1, n2]);

    expect(groups).toHaveLength(1);
    expect(groups[0].count).toBe(2);
    expect(groups[0].latest.id).toBe(2); // newest first
  });

  it('does NOT group notifications outside the 60min window', () => {
    const n1 = makeNotification({ id: 1, created_at: '2026-01-01T10:00:00Z', category: 'system', notification_type: 'backup' });
    const n2 = makeNotification({ id: 2, created_at: '2026-01-01T12:00:00Z', category: 'system', notification_type: 'backup' });

    const groups = groupNotifications([n1, n2]);

    expect(groups).toHaveLength(2);
  });

  it('does NOT group notifications with different category or type', () => {
    const n1 = makeNotification({ id: 1, created_at: '2026-01-01T12:00:00Z', category: 'system', notification_type: 'backup' });
    const n2 = makeNotification({ id: 2, created_at: '2026-01-01T12:10:00Z', category: 'system', notification_type: 'update' });
    const n3 = makeNotification({ id: 3, created_at: '2026-01-01T12:10:00Z', category: 'security', notification_type: 'backup' });

    const groups = groupNotifications([n1, n2, n3]);

    expect(groups).toHaveLength(3);
  });

  it('sets correct group key format', () => {
    const n = makeNotification({ id: 5, created_at: '2026-01-01T12:00:00Z', category: 'security', notification_type: 'login' });
    const groups = groupNotifications([n]);

    expect(groups[0].key).toBe('security:login:5');
  });

  it('handles mixed groupable and ungroupable notifications', () => {
    const base = '2026-01-01T12:00:00Z';
    const notifications = [
      makeNotification({ id: 1, created_at: base, category: 'system', notification_type: 'backup' }),
      makeNotification({ id: 2, created_at: '2026-01-01T12:05:00Z', category: 'system', notification_type: 'backup' }),
      makeNotification({ id: 3, created_at: '2026-01-01T12:10:00Z', category: 'security', notification_type: 'login' }),
    ];

    const groups = groupNotifications(notifications);

    expect(groups).toHaveLength(2);
    const backupGroup = groups.find(g => g.key.startsWith('system:backup'));
    expect(backupGroup?.count).toBe(2);
  });
});
