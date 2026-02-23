/**
 * Notifications Archive Page
 *
 * Full paginated list of all notifications with filters.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell, CheckCheck, Settings, Filter, ChevronLeft, ChevronRight, Clock, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNotifications,
  markAllAsRead,
  markAsRead,
  dismissNotification,
  snoozeNotification,
  getTypeStyle,
  getCategoryIcon,
  getCategoryName,
  getActionLabel,
  type Notification,
  type NotificationCategory,
  type NotificationType,
  type NotificationListResponse,
} from '../api/notifications';

const CATEGORIES: NotificationCategory[] = [
  'raid', 'smart', 'backup', 'scheduler', 'system', 'security', 'sync', 'vpn',
];

const TYPES: NotificationType[] = ['info', 'warning', 'critical'];

const PAGE_SIZE = 50;

export default function NotificationsArchivePage() {
  const navigate = useNavigate();
  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<NotificationCategory | ''>('');
  const [typeFilter, setTypeFilter] = useState<NotificationType | ''>('');
  const [readFilter, setReadFilter] = useState<'' | 'unread' | 'all'>('');

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getNotifications({
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        notification_type: typeFilter || undefined,
        unread_only: readFilter === 'unread',
        include_dismissed: readFilter === 'all',
      });
      setData(result);
    } catch {
      toast.error('Fehler beim Laden der Benachrichtigungen');
    } finally {
      setLoading(false);
    }
  }, [page, categoryFilter, typeFilter, readFilter]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleMarkAllRead = async () => {
    try {
      await markAllAsRead(categoryFilter || undefined);
      toast.success('Alle als gelesen markiert');
      fetchNotifications();
    } catch {
      toast.error('Fehler');
    }
  };

  const handleMarkRead = async (n: Notification) => {
    if (n.is_read) return;
    try {
      await markAsRead(n.id);
      fetchNotifications();
    } catch { /* non-critical */ }
  };

  const handleDismiss = async (n: Notification) => {
    try {
      await dismissNotification(n.id);
      fetchNotifications();
    } catch { /* non-critical */ }
  };

  const handleSnooze = async (n: Notification, hours: number) => {
    try {
      await snoozeNotification(n.id, hours);
      toast.success(`${hours}h snoozed`);
      fetchNotifications();
    } catch {
      toast.error('Snooze fehlgeschlagen');
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Benachrichtigungen</h1>
          <p className="text-sm text-slate-400">
            {data ? `${data.total} gesamt, ${data.unread_count} ungelesen` : 'Laden...'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleMarkAllRead}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            <CheckCheck className="h-4 w-4" />
            Alle gelesen
          </button>
          <button
            onClick={() => navigate('/settings/notifications')}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            <Settings className="h-4 w-4" />
            Einstellungen
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <Filter className="h-4 w-4 text-slate-400" />

        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value as NotificationCategory | ''); setPage(1); }}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">Alle Kategorien</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{getCategoryIcon(c)} {getCategoryName(c)}</option>
          ))}
        </select>

        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value as NotificationType | ''); setPage(1); }}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">Alle Typen</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
          ))}
        </select>

        <select
          value={readFilter}
          onChange={(e) => { setReadFilter(e.target.value as '' | 'unread' | 'all'); setPage(1); }}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">Standard</option>
          <option value="unread">Nur ungelesen</option>
          <option value="all">Inkl. ausgeblendet</option>
        </select>
      </div>

      {/* Notification List */}
      <div className="space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          </div>
        ) : !data || data.notifications.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Bell className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p>Keine Benachrichtigungen gefunden</p>
          </div>
        ) : (
          data.notifications.map((n) => (
            <NotificationRow
              key={n.id}
              notification={n}
              onMarkRead={handleMarkRead}
              onDismiss={handleDismiss}
              onSnooze={handleSnooze}
              onNavigate={(url) => navigate(url)}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-slate-700 p-2 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-slate-400">
            Seite {page} von {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded-lg border border-slate-700 p-2 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

/** Individual notification row with actions */
function NotificationRow({
  notification: n,
  onMarkRead,
  onDismiss,
  onSnooze,
  onNavigate,
}: {
  notification: Notification;
  onMarkRead: (n: Notification) => void;
  onDismiss: (n: Notification) => void;
  onSnooze: (n: Notification, hours: number) => void;
  onNavigate: (url: string) => void;
}) {
  const [showSnooze, setShowSnooze] = useState(false);
  const typeStyle = getTypeStyle(n.notification_type);

  return (
    <div
      className={`group relative flex items-start gap-4 rounded-xl border px-4 py-3 transition ${
        !n.is_read
          ? 'border-slate-700 bg-slate-800/50'
          : 'border-slate-800/50 bg-slate-900/30'
      }`}
    >
      {/* Icon */}
      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}>
        <span className="text-lg">{getCategoryIcon(n.category)}</span>
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm font-medium ${!n.is_read ? 'text-slate-100' : 'text-slate-300'}`}>
            {n.title}
          </p>
          <span className="flex-shrink-0 text-xs text-slate-500">{n.time_ago}</span>
        </div>
        <p className="mt-0.5 text-xs text-slate-400">{n.message}</p>
        <div className="mt-1.5 flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${typeStyle.bgColor} ${typeStyle.color}`}>
            {n.notification_type}
          </span>
          <span className="text-[10px] text-slate-500">{getCategoryName(n.category)}</span>
          {n.snoozed_until && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">
              <Clock className="h-3 w-3" />
              Snoozed bis {new Date(n.snoozed_until).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-shrink-0 items-center gap-1">
        {n.action_url && (
          <button
            onClick={() => onNavigate(n.action_url!)}
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            {getActionLabel(n.category)}
          </button>
        )}

        {/* Snooze */}
        <div className="relative">
          <button
            onClick={() => setShowSnooze(!showSnooze)}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
            title="Snooze"
          >
            <Clock className="h-4 w-4" />
          </button>
          {showSnooze && (
            <div className="absolute right-0 top-8 z-10 rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl">
              {[1, 4, 24].map((h) => (
                <button
                  key={h}
                  onClick={() => { onSnooze(n, h); setShowSnooze(false); }}
                  className="block w-full px-4 py-1.5 text-left text-xs text-slate-300 transition hover:bg-slate-700"
                >
                  {h}h
                </button>
              ))}
            </div>
          )}
        </div>

        {!n.is_read && (
          <button
            onClick={() => onMarkRead(n)}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
            title="Als gelesen markieren"
          >
            <CheckCheck className="h-4 w-4" />
          </button>
        )}

        <button
          onClick={() => onDismiss(n)}
          className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
          title="Ausblenden"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
