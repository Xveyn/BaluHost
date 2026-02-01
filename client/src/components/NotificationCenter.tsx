/**
 * Notification Center Component
 *
 * Displays a bell icon with unread count badge and a dropdown showing recent notifications.
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, X, Settings, ChevronRight } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNotifications,
  getUnreadCount,
  markAsRead,
  markAllAsRead,
  dismissNotification,
  getTypeStyle,
  getCategoryIcon,
  getCategoryName,
  type Notification,
} from '../api/notifications';
import { useNotificationSocket } from '../hooks/useNotificationSocket';

interface NotificationCenterProps {
  className?: string;
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({ className = '' }) => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // WebSocket connection for real-time updates
  const { isConnected } = useNotificationSocket({
    enabled: true,
    onNotification: (notification) => {
      // Add new notification to the list
      setNotifications((prev) => [notification, ...prev.slice(0, 49)]);
      // Show toast for critical/warning notifications
      if (notification.notification_type === 'critical') {
        toast.error(notification.title, { duration: 5000 });
      } else if (notification.notification_type === 'warning') {
        toast(notification.title, { icon: '⚠️', duration: 4000 });
      }
    },
    onUnreadCountChange: (count) => {
      setUnreadCount(count);
    },
  });

  // Fetch initial data
  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const [notifResponse, countResponse] = await Promise.all([
        getNotifications({ page_size: 20 }),
        getUnreadCount(),
      ]);
      setNotifications(notifResponse.notifications);
      setUnreadCount(countResponse.count);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Handle notification click
  const handleNotificationClick = async (notification: Notification) => {
    // Mark as read
    if (!notification.is_read) {
      try {
        await markAsRead(notification.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    }

    // Navigate if action URL exists
    if (notification.action_url) {
      setIsOpen(false);
      navigate(notification.action_url);
    }
  };

  // Handle mark all as read
  const handleMarkAllAsRead = async () => {
    try {
      await markAllAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      toast.success('Alle Benachrichtigungen als gelesen markiert');
    } catch (error) {
      console.error('Failed to mark all as read:', error);
      toast.error('Fehler beim Markieren');
    }
  };

  // Handle dismiss
  const handleDismiss = async (e: React.MouseEvent, notification: Notification) => {
    e.stopPropagation();
    try {
      await dismissNotification(notification.id);
      setNotifications((prev) => prev.filter((n) => n.id !== notification.id));
      if (!notification.is_read) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    } catch (error) {
      console.error('Failed to dismiss notification:', error);
    }
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
        title="Benachrichtigungen"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
        {isConnected && (
          <span className="absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full bg-green-500" title="Verbunden" />
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 top-12 z-50 w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-800 bg-slate-900/95 shadow-xl backdrop-blur-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-100">Benachrichtigungen</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllAsRead}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                  title="Alle als gelesen markieren"
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                  Alle gelesen
                </button>
              )}
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/settings/notifications');
                }}
                className="flex items-center justify-center rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                title="Einstellungen"
              >
                <Settings className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Notification List */}
          <div className="max-h-96 overflow-y-auto">
            {loading && notifications.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center text-slate-400">
                <Bell className="mx-auto mb-2 h-8 w-8 opacity-50" />
                <p className="text-sm">Keine Benachrichtigungen</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-800">
                {notifications.map((notification) => {
                  const typeStyle = getTypeStyle(notification.notification_type);
                  const categoryIcon = getCategoryIcon(notification.category);

                  return (
                    <div
                      key={notification.id}
                      onClick={() => handleNotificationClick(notification)}
                      className={`group relative flex cursor-pointer gap-3 px-4 py-3 transition hover:bg-slate-800/50 ${
                        !notification.is_read ? 'bg-slate-800/30' : ''
                      }`}
                    >
                      {/* Unread indicator */}
                      {!notification.is_read && (
                        <div className="absolute left-1.5 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-sky-500" />
                      )}

                      {/* Icon */}
                      <div
                        className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}
                      >
                        <span className="text-lg">{categoryIcon}</span>
                      </div>

                      {/* Content */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p
                            className={`text-sm font-medium ${
                              !notification.is_read ? 'text-slate-100' : 'text-slate-300'
                            }`}
                          >
                            {notification.title}
                          </p>
                          <span className="flex-shrink-0 text-xs text-slate-500">
                            {notification.time_ago}
                          </span>
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-xs text-slate-400">
                          {notification.message}
                        </p>
                        <div className="mt-1.5 flex items-center gap-2">
                          <span
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${typeStyle.bgColor} ${typeStyle.color}`}
                          >
                            {notification.notification_type}
                          </span>
                          <span className="text-[10px] text-slate-500">
                            {getCategoryName(notification.category)}
                          </span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-shrink-0 items-center gap-1 opacity-0 transition group-hover:opacity-100">
                        {notification.action_url && (
                          <ChevronRight className="h-4 w-4 text-slate-500" />
                        )}
                        <button
                          onClick={(e) => handleDismiss(e, notification)}
                          className="rounded p-1 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
                          title="Verwerfen"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="border-t border-slate-800 p-2">
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/notifications');
                }}
                className="w-full rounded-lg py-2 text-center text-sm text-sky-400 transition hover:bg-slate-800"
              >
                Alle Benachrichtigungen anzeigen
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
