/**
 * Activity Tab Component
 *
 * Displays audit logs with timeline grouping and filtering.
 * Modern timeline view for user activity monitoring.
 */

import { useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../../lib/api';
import {
  RefreshCw,
  CheckCircle,
  XCircle,
  UserCheck,
  LogOut,
  Upload,
  Download,
  Trash2,
  FolderPlus,
  Share2,
  Shield,
  Settings,
  ChevronDown,
  ChevronUp,
  Clock,
  Activity,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { formatDateTime } from '../../lib/dateUtils';

interface AuditLog {
  id: number;
  action: string;
  timestamp: string;
  details: Record<string, any>;
  success: boolean;
  user?: string;
  username?: string;
}

interface AuditLogResponse {
  logs: AuditLog[];
  total: number;
}

interface User {
  username: string;
  role: string;
}

interface ActivityTabProps {
  user?: User;
}

// Action icon mapping
const getActionIcon = (action: string) => {
  const normalizedAction = action.toLowerCase().replace(/_/g, ' ');

  if (normalizedAction.includes('login')) return UserCheck;
  if (normalizedAction.includes('logout')) return LogOut;
  if (normalizedAction.includes('upload')) return Upload;
  if (normalizedAction.includes('download')) return Download;
  if (normalizedAction.includes('delete')) return Trash2;
  if (normalizedAction.includes('create') || normalizedAction.includes('folder')) return FolderPlus;
  if (normalizedAction.includes('share')) return Share2;
  if (normalizedAction.includes('security') || normalizedAction.includes('auth')) return Shield;
  if (normalizedAction.includes('setting') || normalizedAction.includes('config')) return Settings;

  return Activity;
};

// Action color mapping
const getActionColor = (action: string) => {
  const normalizedAction = action.toLowerCase().replace(/_/g, ' ');

  if (normalizedAction.includes('login')) return 'text-green-400 bg-green-500/20 border-green-500/40';
  if (normalizedAction.includes('logout')) return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/40';
  if (normalizedAction.includes('upload') || normalizedAction.includes('create')) return 'text-blue-400 bg-blue-500/20 border-blue-500/40';
  if (normalizedAction.includes('download')) return 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40';
  if (normalizedAction.includes('delete')) return 'text-red-400 bg-red-500/20 border-red-500/40';
  if (normalizedAction.includes('share')) return 'text-purple-400 bg-purple-500/20 border-purple-500/40';

  return 'text-slate-400 bg-slate-500/20 border-slate-500/40';
};

export function ActivityTab({ user }: ActivityTabProps) {
  const { t } = useTranslation(['system', 'common']);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [userFilter, setUserFilter] = useState<string>('');
  const [expandedLogs, setExpandedLogs] = useState<Set<number>>(new Set());
  const [totalCount, setTotalCount] = useState(0);

  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    loadAuditLogs();
  }, [actionFilter, userFilter]);

  const loadAuditLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {
        limit: 100,
        sort_order: 'desc',
      };

      if (actionFilter) {
        params.action_filter = actionFilter;
      }
      if (userFilter) {
        params.user_filter = userFilter;
      }

      const response = await apiClient.get<AuditLogResponse>('/api/logging/audit', { params });
      setAuditLogs(response.data.logs || []);
      setTotalCount(response.data.total || response.data.logs?.length || 0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('monitor.activity.loadError');
      setError(msg);
      toast.error(t('monitor.activity.loadError'));
    } finally {
      setLoading(false);
    }
  };

  const toggleLogExpanded = (logId: number) => {
    setExpandedLogs((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(logId)) {
        newSet.delete(logId);
      } else {
        newSet.add(logId);
      }
      return newSet;
    });
  };

  // Group logs by time periods
  const groupedLogs = useMemo(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const thisWeekStart = new Date(today);
    thisWeekStart.setDate(thisWeekStart.getDate() - 7);

    const groups: { label: string; logs: AuditLog[] }[] = [
      { label: t('monitor.activity.today'), logs: [] },
      { label: t('monitor.activity.yesterday'), logs: [] },
      { label: t('monitor.activity.thisWeek'), logs: [] },
      { label: t('monitor.activity.earlier'), logs: [] },
    ];

    auditLogs.forEach((log) => {
      const logDate = new Date(log.timestamp);
      if (logDate >= today) {
        groups[0].logs.push(log);
      } else if (logDate >= yesterday) {
        groups[1].logs.push(log);
      } else if (logDate >= thisWeekStart) {
        groups[2].logs.push(log);
      } else {
        groups[3].logs.push(log);
      }
    });

    return groups.filter((group) => group.logs.length > 0);
  }, [auditLogs, t]);

  // Get unique actions and users for filters
  const availableActions = useMemo(() => {
    return Array.from(new Set(auditLogs.map((log) => log.action))).sort();
  }, [auditLogs]);

  const availableUsers = useMemo(() => {
    return Array.from(
      new Set(auditLogs.map((log) => log.user || log.username).filter(Boolean))
    ).sort() as string[];
  }, [auditLogs]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">{t('common:loading')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card border-red-900/60 bg-red-950/30 p-4">
        <p className="font-bold text-red-400">{t('common:error')}</p>
        <p className="text-red-300">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">{t('monitor.activity.title')}</h2>
          <p className="text-xs sm:text-sm text-slate-400">
            {t('monitor.activity.description')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">{t('monitor.activity.allActions')}</option>
            {availableActions.map((action) => (
              <option key={action} value={action}>
                {action.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          {isAdmin && (
            <select
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">{t('monitor.activity.allUsers')}</option>
              {availableUsers.map((user) => (
                <option key={user} value={user}>
                  {user}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={loadAuditLogs}
            className="btn btn-primary flex items-center gap-2 justify-center touch-manipulation active:scale-95"
          >
            <RefreshCw className="h-4 w-4" />
            <span className="hidden sm:inline">{t('common:refresh')}</span>
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        {groupedLogs.length > 0 ? (
          <div className="space-y-6">
            {groupedLogs.map((group) => (
              <div key={group.label}>
                {/* Time Group Header */}
                <div className="flex items-center gap-3 mb-4">
                  <Clock className="h-4 w-4 text-slate-500" />
                  <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider">
                    {group.label}
                  </h3>
                  <div className="flex-1 border-t border-slate-800/60"></div>
                </div>

                {/* Desktop Timeline View */}
                <div className="hidden lg:block space-y-3">
                  {group.logs.map((log) => {
                    const IconComponent = getActionIcon(log.action);
                    const colorClass = getActionColor(log.action);
                    const isExpanded = expandedLogs.has(log.id);
                    const hasDetails = Object.keys(log.details || {}).length > 0;
                    const displayUser = log.user || log.username;

                    return (
                      <div
                        key={log.id}
                        className="flex items-start gap-4 p-4 rounded-xl border border-slate-800/60 bg-slate-950/70 hover:bg-slate-950/90 transition-colors"
                      >
                        {/* Icon */}
                        <div className={`p-2 rounded-lg border ${colorClass}`}>
                          <IconComponent className="h-4 w-4" />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3 flex-wrap">
                            <span className="font-medium text-white">
                              {log.action.replace(/_/g, ' ')}
                            </span>
                            {displayUser && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-300">
                                {displayUser}
                              </span>
                            )}
                            {log.success ? (
                              <span className="inline-flex items-center gap-1 text-xs text-green-400">
                                <CheckCircle className="h-3 w-3" />
                                {t('monitor.activity.success')}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-xs text-red-400">
                                <XCircle className="h-3 w-3" />
                                {t('monitor.activity.failed')}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 mt-1">
                            {formatDateTime(log.timestamp)}
                          </p>

                          {/* Expandable Details */}
                          {hasDetails && (
                            <div className="mt-2">
                              <button
                                onClick={() => toggleLogExpanded(log.id)}
                                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300 transition-colors"
                              >
                                {isExpanded ? (
                                  <>
                                    <ChevronUp className="h-3 w-3" />
                                    {t('monitor.activity.hideDetails')}
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown className="h-3 w-3" />
                                    {t('monitor.activity.viewDetails')}
                                  </>
                                )}
                              </button>
                              {isExpanded && (
                                <pre className="mt-2 p-3 rounded-lg bg-slate-900/70 border border-slate-800/60 text-xs text-emerald-400 overflow-x-auto">
                                  {JSON.stringify(log.details, null, 2)}
                                </pre>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Mobile Card View */}
                <div className="lg:hidden space-y-3">
                  {group.logs.map((log) => {
                    const IconComponent = getActionIcon(log.action);
                    const colorClass = getActionColor(log.action);
                    const isExpanded = expandedLogs.has(log.id);
                    const hasDetails = Object.keys(log.details || {}).length > 0;
                    const displayUser = log.user || log.username;

                    return (
                      <div
                        key={log.id}
                        className="p-4 rounded-xl border border-slate-800/60 bg-slate-950/70"
                      >
                        <div className="flex items-start gap-3">
                          <div className={`p-2 rounded-lg border ${colorClass}`}>
                            <IconComponent className="h-4 w-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-medium text-white text-sm">
                                {log.action.replace(/_/g, ' ')}
                              </span>
                              {log.success ? (
                                <CheckCircle className="h-4 w-4 text-green-400 flex-shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                              {displayUser && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-300">
                                  {displayUser}
                                </span>
                              )}
                              <span className="text-xs text-slate-500">
                                {formatDateTime(log.timestamp)}
                              </span>
                            </div>

                            {hasDetails && (
                              <div className="mt-2">
                                <button
                                  onClick={() => toggleLogExpanded(log.id)}
                                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300 transition-colors"
                                >
                                  {isExpanded ? (
                                    <>
                                      <ChevronUp className="h-3 w-3" />
                                      {t('monitor.activity.hideDetails')}
                                    </>
                                  ) : (
                                    <>
                                      <ChevronDown className="h-3 w-3" />
                                      {t('monitor.activity.viewDetails')}
                                    </>
                                  )}
                                </button>
                                {isExpanded && (
                                  <pre className="mt-2 p-3 rounded-lg bg-slate-900/70 border border-slate-800/60 text-xs text-emerald-400 overflow-x-auto">
                                    {JSON.stringify(log.details, null, 2)}
                                  </pre>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-slate-400">
            <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>{t('monitor.activity.noActivity')}</p>
          </div>
        )}

        {totalCount > auditLogs.length && (
          <div className="mt-4 text-center text-sm text-slate-400">
            {t('monitor.activity.showingOfTotal', { shown: auditLogs.length, total: totalCount })}
          </div>
        )}
      </div>
    </div>
  );
}
