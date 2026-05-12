/**
 * Notifications Archive Page
 *
 * Full paginated list of notifications with Inbox / Trash tabs and filters.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Bell, CheckCheck, Settings, Filter, ChevronLeft, ChevronRight, Clock,
  X, Trash2, RotateCcw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNotifications,
  getTrashNotifications,
  restoreNotification,
  deleteNotificationPermanently,
  emptyTrash as apiEmptyTrash,
  getPreferences,
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
import { useNotifications } from '../contexts/NotificationContext';

const CATEGORIES: NotificationCategory[] = [
  'raid', 'smart', 'backup', 'scheduler', 'system', 'security', 'sync', 'vpn', 'lifecycle',
];

const TYPES: NotificationType[] = ['info', 'warning', 'critical'];

const PAGE_SIZE = 50;

type TabKey = 'inbox' | 'trash';

export default function NotificationsArchivePage() {
  const { t } = useTranslation(['notifications', 'common']);
  const navigate = useNavigate();
  const {
    markAsRead: ctxMarkAsRead,
    markAllAsRead: ctxMarkAllAsRead,
    dismiss: ctxDismiss,
    dismissAll: ctxDismissAll,
    refresh: ctxRefresh,
  } = useNotifications();

  const [tab, setTab] = useState<TabKey>('inbox');
  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [retentionDays, setRetentionDays] = useState<number>(7);

  const [categoryFilter, setCategoryFilter] = useState<NotificationCategory | ''>('');
  const [typeFilter, setTypeFilter] = useState<NotificationType | ''>('');
  const [readFilter, setReadFilter] = useState<'' | 'unread'>('');

  useEffect(() => {
    getPreferences()
      .then((p) => setRetentionDays(p.trash_retention_days ?? 7))
      .catch(() => setRetentionDays(7));
  }, []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        notification_type: typeFilter || undefined,
      };
      const result =
        tab === 'inbox'
          ? await getNotifications({
              ...params,
              unread_only: readFilter === 'unread',
            })
          : await getTrashNotifications(params);
      setData(result);
    } catch {
      toast.error(t('common:toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [tab, page, categoryFilter, typeFilter, readFilter, t]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  useEffect(() => {
    setPage(1);
  }, [tab, categoryFilter, typeFilter, readFilter]);

  const handleMarkAllRead = async () => {
    try {
      await ctxMarkAllAsRead();
      toast.success(t('toast.markedAllRead'));
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleDismissAll = async () => {
    if (!data || data.total === 0) return;
    if (!window.confirm(t('toast.confirmDismissAll', { count: data.total }))) return;
    try {
      await ctxDismissAll();
      toast.success(t('toast.movedToTrash'));
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleEmptyTrash = async () => {
    if (!data || data.total === 0) return;
    if (!window.confirm(t('trash.emptyConfirm', { count: data.total }))) return;
    try {
      const { count } = await apiEmptyTrash();
      toast.success(t('trash.emptied'));
      fetchList();
      if (count > 0) ctxRefresh();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const handleMarkRead = async (n: Notification) => {
    if (n.is_read) return;
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.map((x) =>
        x.id === n.id ? { ...x, is_read: true } : x
      ),
      unread_count: Math.max(0, prev.unread_count - 1),
    }));
    try { await ctxMarkAsRead(n.id); } catch { /* non-critical */ }
  };

  const handleDismiss = async (n: Notification) => {
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
      unread_count: !n.is_read ? Math.max(0, prev.unread_count - 1) : prev.unread_count,
    }));
    try {
      await ctxDismiss(n.id);
    } catch {
      fetchList();
    }
  };

  const handleRestore = async (n: Notification) => {
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
    }));
    try {
      await restoreNotification(n.id);
      toast.success(t('trash.restored'));
      ctxRefresh();
    } catch {
      toast.error(t('common:toast.error'));
      fetchList();
    }
  };

  const handleDeleteForever = async (n: Notification) => {
    if (!window.confirm(t('trash.deleteForeverConfirm'))) return;
    setData((prev) => prev && ({
      ...prev,
      notifications: prev.notifications.filter((x) => x.id !== n.id),
      total: prev.total - 1,
    }));
    try {
      await deleteNotificationPermanently(n.id);
      toast.success(t('trash.deleted'));
    } catch {
      toast.error(t('common:toast.error'));
      fetchList();
    }
  };

  const handleSnooze = async (n: Notification, hours: number) => {
    try {
      await snoozeNotification(n.id, hours);
      toast.success(`${hours}h snoozed`);
      fetchList();
    } catch {
      toast.error(t('common:toast.error'));
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{t('title')}</h1>
          <p className="text-sm text-slate-400">
            {data
              ? `${data.total} ${tab === 'inbox' ? t('count.total') : t('count.inTrash')}${tab === 'inbox' ? `, ${data.unread_count} ${t('count.unread')}` : ''}`
              : t('common:loading')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tab === 'inbox' && (
            <>
              <button
                onClick={handleMarkAllRead}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
              >
                <CheckCheck className="h-4 w-4" />
                {t('buttons.markAllRead')}
              </button>
              <button
                onClick={handleDismissAll}
                disabled={!data || data.total === 0}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-rose-500/50 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" />
                {t('buttons.dismissAll')}
              </button>
            </>
          )}
          {tab === 'trash' && (
            <button
              onClick={handleEmptyTrash}
              disabled={!data || data.total === 0}
              className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 px-3 py-2 text-sm text-rose-400 transition hover:border-rose-500 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" />
              {t('trash.empty')}
            </button>
          )}
          <button
            onClick={() => navigate('/settings?tab=notifications')}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            <Settings className="h-4 w-4" />
            {t('buttons.settings')}
          </button>
        </div>
      </div>

      <div className="flex gap-2 border-b border-slate-800">
        {(['inbox', 'trash'] as TabKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`relative px-4 py-2 text-sm transition ${
              tab === k ? 'text-sky-400' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t(`tabs.${k}`)}
            {tab === k && (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-sky-500" />
            )}
          </button>
        ))}
      </div>

      {tab === 'trash' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2 text-xs text-amber-300">
          {t('trash.banner', { days: retentionDays })}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <Filter className="h-4 w-4 text-slate-400" />

        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as NotificationCategory | '')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">{t('filters.allCategories')}</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{getCategoryIcon(c)} {getCategoryName(c)}</option>
          ))}
        </select>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as NotificationType | '')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">{t('filters.allTypes')}</option>
          {TYPES.map((tp) => (
            <option key={tp} value={tp}>{tp.charAt(0).toUpperCase() + tp.slice(1)}</option>
          ))}
        </select>

        {tab === 'inbox' && (
          <select
            value={readFilter}
            onChange={(e) => setReadFilter(e.target.value as '' | 'unread')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
          >
            <option value="">{t('filters.default')}</option>
            <option value="unread">{t('filters.unreadOnly')}</option>
          </select>
        )}
      </div>

      <div className="space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          </div>
        ) : !data || data.notifications.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Bell className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p>{tab === 'inbox' ? t('empty.inbox') : t('empty.trash')}</p>
          </div>
        ) : (
          data.notifications.map((n) => (
            <NotificationRow
              key={n.id}
              tab={tab}
              notification={n}
              onMarkRead={handleMarkRead}
              onDismiss={handleDismiss}
              onRestore={handleRestore}
              onDeleteForever={handleDeleteForever}
              onSnooze={handleSnooze}
              onNavigate={(url) => navigate(url)}
            />
          ))
        )}
      </div>

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
            {t('pagination.pageOf', { page, total: totalPages })}
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

function NotificationRow({
  tab,
  notification: n,
  onMarkRead,
  onDismiss,
  onRestore,
  onDeleteForever,
  onSnooze,
  onNavigate,
}: {
  tab: TabKey;
  notification: Notification;
  onMarkRead: (n: Notification) => void;
  onDismiss: (n: Notification) => void;
  onRestore: (n: Notification) => void;
  onDeleteForever: (n: Notification) => void;
  onSnooze: (n: Notification, hours: number) => void;
  onNavigate: (url: string) => void;
}) {
  const [showSnooze, setShowSnooze] = useState(false);
  const { t } = useTranslation(['notifications']);
  const typeStyle = getTypeStyle(n.notification_type);

  return (
    <div
      className={`group relative flex items-start gap-4 rounded-xl border px-4 py-3 transition ${
        !n.is_read
          ? 'border-slate-700 bg-slate-800/50'
          : 'border-slate-800/50 bg-slate-900/30'
      }`}
    >
      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border ${typeStyle.bgColor}`}>
        <span className="text-lg">{getCategoryIcon(n.category)}</span>
      </div>

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

      <div className="flex flex-shrink-0 items-center gap-1">
        {n.action_url && tab === 'inbox' && (
          <button
            onClick={() => onNavigate(n.action_url!)}
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            {getActionLabel(n.category)}
          </button>
        )}

        {tab === 'inbox' && (
          <>
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
                title={t('buttons.markRead')}
              >
                <CheckCheck className="h-4 w-4" />
              </button>
            )}

            <button
              onClick={() => onDismiss(n)}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-slate-300"
              title={t('buttons.moveToTrash')}
            >
              <X className="h-4 w-4" />
            </button>
          </>
        )}

        {tab === 'trash' && (
          <>
            <button
              onClick={() => onRestore(n)}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700 hover:text-sky-400"
              title={t('trash.restore')}
            >
              <RotateCcw className="h-4 w-4" />
            </button>
            <button
              onClick={() => onDeleteForever(n)}
              className="rounded-lg p-1.5 text-rose-500 transition hover:bg-rose-500/10 hover:text-rose-400"
              title={t('trash.deleteForever')}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
