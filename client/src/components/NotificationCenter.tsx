/**
 * Notification Center Component
 *
 * Displays a bell icon with unread count badge and a dropdown showing recent notifications.
 * Supports grouping, snooze, and inline action buttons.
 * Consumes NotificationContext (WS + state live above route level).
 */
import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, X, Settings, ChevronRight, ChevronDown, Clock } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getTypeStyle,
  getCategoryIcon,
  getCategoryName,
  getActionLabel,
  snoozeNotification,
  type Notification,
} from '../api/notifications';
import { useNotifications } from '../contexts/NotificationContext';
import { groupNotifications, type NotificationGroup } from '../lib/notificationGrouping';

interface NotificationCenterProps {
  className?: string;
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({ className = '' }) => {
  const { t } = useTranslation('notifications');
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const dropdownRef = useRef<HTMLDivElement>(null);

  const {
    notifications,
    unreadCount,
    loading,
    isConnected,
    markAsRead,
    markAllAsRead,
    dismiss,
    refresh,
  } = useNotifications();

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

  // Group notifications
  const groups = groupNotifications(notifications);

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Handle notification click
  const handleNotificationClick = async (notification: Notification) => {
    if (!notification.is_read) {
      await markAsRead(notification.id);
    }
    if (notification.action_url) {
      setIsOpen(false);
      navigate(notification.action_url);
    }
  };

  // Handle mark all as read
  const handleMarkAllAsRead = async () => {
    try {
      await markAllAsRead();
      toast.success(t('markedAllRead'));
    } catch {
      toast.error(t('markError'));
    }
  };

  // Handle dismiss
  const handleDismiss = async (e: React.MouseEvent, notification: Notification) => {
    e.stopPropagation();
    try {
      await dismiss(notification.id);
    } catch {
      // Non-critical
    }
  };

  // Handle snooze
  const handleSnooze = async (e: React.MouseEvent, notification: Notification, hours: number) => {
    e.stopPropagation();
    try {
      await snoozeNotification(notification.id, hours);
      toast.success(`${hours}h snoozed`);
      if (refresh) refresh();
    } catch {
      toast.error('Snooze fehlgeschlagen');
    }
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
        title={t('title')}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
        {isConnected && (
          <span className="absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full bg-green-500" title={t('connected')} />
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 top-12 z-50 w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-800 bg-slate-900/95 shadow-xl backdrop-blur-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-100">{t('title')}</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllAsRead}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                  title={t('markAllRead')}
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                  {t('allRead')}
                </button>
              )}
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/settings?tab=notifications');
                }}
                className="flex items-center justify-center rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                title={t('settings')}
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
            ) : groups.length === 0 ? (
              <div className="py-8 text-center text-slate-400">
                <Bell className="mx-auto mb-2 h-8 w-8 opacity-50" />
                <p className="text-sm">{t('noNotifications')}</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-800">
                {groups.map((group) => (
                  <GroupedNotification
                    key={group.key}
                    group={group}
                    isExpanded={expandedGroups.has(group.key)}
                    onToggle={() => toggleGroup(group.key)}
                    onClick={handleNotificationClick}
                    onDismiss={handleDismiss}
                    onSnooze={handleSnooze}
                  />
                ))}
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
                {t('viewAll')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** Render a single group (may be 1 item or a collapsed group) */
function GroupedNotification({
  group,
  isExpanded,
  onToggle,
  onClick,
  onDismiss,
  onSnooze,
}: {
  group: NotificationGroup;
  isExpanded: boolean;
  onToggle: () => void;
  onClick: (n: Notification) => void;
  onDismiss: (e: React.MouseEvent, n: Notification) => void;
  onSnooze: (e: React.MouseEvent, n: Notification, hours: number) => void;
}) {
  // Single notification - render directly
  if (group.count === 1) {
    return (
      <SingleNotification
        notification={group.latest}
        onClick={onClick}
        onDismiss={onDismiss}
        onSnooze={onSnooze}
      />
    );
  }

  // Grouped notifications
  const typeStyle = getTypeStyle(group.latest.notification_type);
  const categoryIcon = getCategoryIcon(group.latest.category);

  return (
    <div>
      {/* Group header */}
      <div
        onClick={onToggle}
        className="flex cursor-pointer items-center gap-3 px-4 py-3 transition hover:bg-slate-800/50"
      >
        <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}>
          <span className="text-lg">{categoryIcon}</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-100">
            {group.count} {getCategoryName(group.latest.category)} {group.latest.notification_type === 'warning' ? 'Warnungen' : 'Meldungen'}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">{group.latest.title}</p>
        </div>
        <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isExpanded ? 'rotate-180' : ''}`} />
      </div>

      {/* Expanded items */}
      {isExpanded && (
        <div className="border-t border-slate-800/50 bg-slate-900/50">
          {group.items.map((n) => (
            <SingleNotification
              key={n.id}
              notification={n}
              onClick={onClick}
              onDismiss={onDismiss}
              onSnooze={onSnooze}
              compact
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Render a single notification item */
function SingleNotification({
  notification,
  onClick,
  onDismiss,
  onSnooze,
  compact = false,
}: {
  notification: Notification;
  onClick: (n: Notification) => void;
  onDismiss: (e: React.MouseEvent, n: Notification) => void;
  onSnooze: (e: React.MouseEvent, n: Notification, hours: number) => void;
  compact?: boolean;
}) {
  const [showSnooze, setShowSnooze] = useState(false);
  const typeStyle = getTypeStyle(notification.notification_type);
  const categoryIcon = getCategoryIcon(notification.category);

  return (
    <div
      onClick={() => onClick(notification)}
      className={`group relative flex cursor-pointer gap-3 px-4 py-3 transition hover:bg-slate-800/50 ${
        !notification.is_read ? 'bg-slate-800/30' : ''
      } ${compact ? 'pl-8' : ''}`}
    >
      {/* Unread indicator */}
      {!notification.is_read && (
        <div className="absolute left-1.5 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-sky-500" />
      )}

      {/* Icon */}
      {!compact && (
        <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}>
          <span className="text-lg">{categoryIcon}</span>
        </div>
      )}

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm font-medium ${!notification.is_read ? 'text-slate-100' : 'text-slate-300'}`}>
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
          <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${typeStyle.bgColor} ${typeStyle.color}`}>
            {notification.notification_type}
          </span>
          <span className="text-[10px] text-slate-500">
            {getCategoryName(notification.category)}
          </span>
          {notification.snoozed_until && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-400">
              <Clock className="h-3 w-3" />
              Snoozed
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-shrink-0 items-center gap-1 opacity-0 transition group-hover:opacity-100">
        {notification.action_url && (
          <span className="text-[10px] text-sky-400">{getActionLabel(notification.category)}</span>
        )}
        {notification.action_url && (
          <ChevronRight className="h-4 w-4 text-slate-500" />
        )}

        {/* Snooze button */}
        <div className="relative">
          <button
            onClick={(e) => { e.stopPropagation(); setShowSnooze(!showSnooze); }}
            className="rounded p-1 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
            title="Snooze"
          >
            <Clock className="h-3.5 w-3.5" />
          </button>
          {showSnooze && (
            <div className="absolute right-0 top-7 z-20 rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl">
              {[1, 4, 24].map((h) => (
                <button
                  key={h}
                  onClick={(e) => { onSnooze(e, notification, h); setShowSnooze(false); }}
                  className="block w-full px-3 py-1 text-left text-xs text-slate-300 hover:bg-slate-700"
                >
                  {h}h
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={(e) => onDismiss(e, notification)}
          className="rounded p-1 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
          title="Ausblenden"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export default NotificationCenter;
