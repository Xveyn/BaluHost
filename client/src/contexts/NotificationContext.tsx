/**
 * NotificationContext — holds WS connection + notification state above route level,
 * so route navigation does not tear down the WebSocket.
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  getNotifications,
  getUnreadCount,
  markAsRead as apiMarkAsRead,
  markAllAsRead as apiMarkAllAsRead,
  dismissNotification as apiDismiss,
  type Notification,
} from '../api/notifications';
import { useNotificationSocket } from '../hooks/useNotificationSocket';
import { useAuth } from './AuthContext';
import { isPi } from '../lib/features';

interface NotificationContextValue {
  notifications: Notification[];
  unreadCount: number;
  loading: boolean;
  isConnected: boolean;
  markAsRead: (id: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  dismiss: (id: number) => Promise<void>;
  refresh: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);

  const { isConnected } = useNotificationSocket({
    enabled: !!token && !isPi,
    onNotification: (notification) => {
      setNotifications((prev) => [notification, ...prev.slice(0, 49)]);
      if (notification.notification_type === 'critical') {
        toast.error(notification.title, { duration: 5000 });
      } else if (notification.notification_type === 'warning') {
        toast(notification.title, { icon: '\u26A0\uFE0F', duration: 4000 });
      }
    },
    onUnreadCountChange: (count) => {
      setUnreadCount(count);
    },
  });

  const fetchNotifications = useCallback(async () => {
    if (!token || isPi) return;
    setLoading(true);
    try {
      const [notifResponse, countResponse] = await Promise.all([
        getNotifications({ page_size: 20 }),
        getUnreadCount(),
      ]);
      setNotifications(notifResponse.notifications);
      setUnreadCount(countResponse.count);
    } catch {
      // Non-critical
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Fetch on mount / token change
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Reset state when logged out
  useEffect(() => {
    if (!token) {
      setNotifications([]);
      setUnreadCount(0);
    }
  }, [token]);

  const markAsRead = useCallback(async (id: number) => {
    try {
      await apiMarkAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Non-critical
    }
  }, []);

  const markAllAsRead = useCallback(async () => {
    await apiMarkAllAsRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  }, []);

  const dismiss = useCallback(async (id: number) => {
    await apiDismiss(id);
    setNotifications((prev) => {
      const target = prev.find((n) => n.id === id);
      if (target && !target.is_read) {
        setUnreadCount((c) => Math.max(0, c - 1));
      }
      return prev.filter((n) => n.id !== id);
    });
  }, []);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        loading,
        isConnected,
        markAsRead,
        markAllAsRead,
        dismiss,
        refresh: fetchNotifications,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider');
  return ctx;
}
