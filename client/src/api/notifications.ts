/**
 * Notifications API client for BaluHost
 */
import { apiClient } from '../lib/api';

// Notification types
export type NotificationType = 'info' | 'warning' | 'critical';
export type NotificationCategory = 'raid' | 'smart' | 'backup' | 'scheduler' | 'system' | 'security' | 'sync' | 'vpn';

export interface Notification {
  id: number;
  created_at: string;
  user_id: number | null;
  notification_type: NotificationType;
  category: NotificationCategory;
  title: string;
  message: string;
  action_url: string | null;
  is_read: boolean;
  is_dismissed: boolean;
  priority: number;
  metadata: Record<string, any> | null;
  time_ago: string | null;
}

export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
}

export interface UnreadCountResponse {
  count: number;
  by_category: Record<string, number> | null;
}

export interface MarkReadResponse {
  success: boolean;
  count: number;
}

export interface CategoryPreference {
  email: boolean;
  push: boolean;
  in_app: boolean;
}

export interface NotificationPreferences {
  id: number;
  user_id: number;
  email_enabled: boolean;
  push_enabled: boolean;
  in_app_enabled: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  min_priority: number;
  category_preferences: Record<string, CategoryPreference> | null;
}

export interface NotificationPreferencesUpdate {
  email_enabled?: boolean;
  push_enabled?: boolean;
  in_app_enabled?: boolean;
  quiet_hours_enabled?: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  min_priority?: number;
  category_preferences?: Record<string, CategoryPreference>;
}

// API Functions

/**
 * Get notifications for the current user
 */
export async function getNotifications(
  options: {
    unread_only?: boolean;
    include_dismissed?: boolean;
    category?: NotificationCategory;
    page?: number;
    page_size?: number;
  } = {}
): Promise<NotificationListResponse> {
  const response = await apiClient.get<NotificationListResponse>('/api/notifications', {
    params: {
      unread_only: options.unread_only ?? false,
      include_dismissed: options.include_dismissed ?? false,
      category: options.category,
      page: options.page ?? 1,
      page_size: options.page_size ?? 50,
    },
  });
  return response.data;
}

/**
 * Get unread notification count for the current user
 */
export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const response = await apiClient.get<UnreadCountResponse>('/api/notifications/unread-count');
  return response.data;
}

/**
 * Mark a specific notification as read
 */
export async function markAsRead(notificationId: number): Promise<Notification> {
  const response = await apiClient.post<Notification>(`/api/notifications/${notificationId}/read`);
  return response.data;
}

/**
 * Mark all notifications as read
 */
export async function markAllAsRead(category?: NotificationCategory): Promise<MarkReadResponse> {
  const response = await apiClient.post<MarkReadResponse>('/api/notifications/read-all', {
    category,
  });
  return response.data;
}

/**
 * Dismiss a notification
 */
export async function dismissNotification(notificationId: number): Promise<Notification> {
  const response = await apiClient.post<Notification>(`/api/notifications/${notificationId}/dismiss`);
  return response.data;
}

/**
 * Get notification preferences for the current user
 */
export async function getPreferences(): Promise<NotificationPreferences> {
  const response = await apiClient.get<NotificationPreferences>('/api/notifications/preferences');
  return response.data;
}

/**
 * Update notification preferences for the current user
 */
export async function updatePreferences(
  preferences: NotificationPreferencesUpdate
): Promise<NotificationPreferences> {
  const response = await apiClient.put<NotificationPreferences>(
    '/api/notifications/preferences',
    preferences
  );
  return response.data;
}

// Helper functions

/**
 * Get type icon and color for notification type
 */
export function getTypeStyle(type: NotificationType): { icon: string; color: string; bgColor: string } {
  switch (type) {
    case 'critical':
      return {
        icon: '🚨',
        color: 'text-rose-400',
        bgColor: 'bg-rose-500/20 border-rose-500/40',
      };
    case 'warning':
      return {
        icon: '⚠️',
        color: 'text-amber-400',
        bgColor: 'bg-amber-500/20 border-amber-500/40',
      };
    case 'info':
    default:
      return {
        icon: 'ℹ️',
        color: 'text-sky-400',
        bgColor: 'bg-sky-500/20 border-sky-500/40',
      };
  }
}

/**
 * Get category icon
 */
export function getCategoryIcon(category: NotificationCategory): string {
  switch (category) {
    case 'raid':
      return '💾';
    case 'smart':
      return '🔧';
    case 'backup':
      return '📦';
    case 'scheduler':
      return '⏰';
    case 'system':
      return '🖥️';
    case 'security':
      return '🔒';
    case 'sync':
      return '🔄';
    case 'vpn':
      return '🔐';
    default:
      return '🔔';
  }
}

/**
 * Get category display name
 */
export function getCategoryName(category: NotificationCategory): string {
  const names: Record<NotificationCategory, string> = {
    raid: 'RAID',
    smart: 'SMART',
    backup: 'Backup',
    scheduler: 'Scheduler',
    system: 'System',
    security: 'Security',
    sync: 'Sync',
    vpn: 'VPN',
  };
  return names[category] || category;
}

/**
 * Get WebSocket URL for notifications
 */
export function getWebSocketUrl(): string {
  const token = localStorage.getItem('token');
  const isDevelopment = import.meta.env.DEV;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = isDevelopment ? '127.0.0.1:3001' : window.location.host;
  return `${protocol}//${host}/api/notifications/ws?token=${token}`;
}
