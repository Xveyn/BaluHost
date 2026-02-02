import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { loggingApi } from '../api/logging';
import type { AuditLoggingStatus, FileAccessLogsResponse } from '../api/logging';
import { RefreshCw, FileText, CheckCircle, XCircle, Power } from 'lucide-react';
import toast from 'react-hot-toast';
import { formatDateTime } from '../lib/dateUtils';

const Logging: React.FC = () => {
  const { t } = useTranslation(['system', 'common']);
  const [fileAccessLogs, setFileAccessLogs] = useState<FileAccessLogsResponse | null>(
    null
  );
  const [auditStatus, setAuditStatus] = useState<AuditLoggingStatus | null>(null);
  const [timeRange, setTimeRange] = useState<number>(24);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [userFilter, setUserFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingAudit, setTogglingAudit] = useState(false);

  useEffect(() => {
    loadData();
  }, [timeRange, actionFilter, userFilter]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [logsData, statusData] = await Promise.all([
        loggingApi.getFileAccessLogs({
          limit: 100,
          days: Math.ceil(timeRange / 24),
          action: actionFilter || undefined,
          user: userFilter || undefined,
        }),
        loggingApi.getAuditLoggingStatus().catch(() => null), // Fail silently if not admin
      ]);

      setFileAccessLogs(logsData);
      setAuditStatus(statusData);
    } catch (err: any) {
      setError(err.message || 'Failed to load logging data');
      console.error('Error loading logging data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAuditLogging = async () => {
    if (!auditStatus) return;

    setTogglingAudit(true);
    try {
      const newStatus = await loggingApi.toggleAuditLogging(!auditStatus.enabled);
      setAuditStatus(newStatus);
      toast.success(
        newStatus.enabled
          ? t('logging.enabledSuccess')
          : t('logging.disabledSuccess')
      );
    } catch (err: any) {
      toast.error(err.message || t('logging.toggleError'));
      console.error('Error toggling audit logging:', err);
    } finally {
      setTogglingAudit(false);
    }
  };

  const formatBytes = (bytes: number | undefined): string => {
    if (!bytes) return '-';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
  };

  // Use centralized UTC timestamp formatting
  const formatTimestamp = formatDateTime;

  const availableActions = Array.from(
    new Set(fileAccessLogs?.logs.map((log) => log.action) || [])
  ).sort();

  const availableUsers = Array.from(
    new Set(fileAccessLogs?.logs.map((log) => log.user) || [])
  ).sort();

  const getActionBadgeClass = (action: string) => {
    if (action === 'read' || action === 'download') {
      return 'border border-green-500/40 bg-green-500/15 text-green-300';
    }
    if (action === 'write' || action === 'upload' || action === 'create') {
      return 'border border-yellow-500/40 bg-yellow-500/15 text-yellow-300';
    }
    if (action === 'delete') {
      return 'border border-rose-500/40 bg-rose-500/15 text-rose-300';
    }
    return 'border border-slate-700/70 bg-slate-900/70 text-slate-300';
  };

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
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('logging.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('logging.description')}
            {auditStatus && (
              <span className={`ml-2 text-xs ${auditStatus.enabled ? 'text-green-400' : 'text-yellow-400'}`}>
                ({auditStatus.enabled ? t('logging.loggingEnabled') : t('logging.loggingDisabled')})
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {auditStatus?.can_toggle && (
            <button
              onClick={handleToggleAuditLogging}
              disabled={togglingAudit}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg border text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                auditStatus.enabled
                  ? 'border-green-500/40 bg-green-500/10 text-green-300 hover:bg-green-500/20'
                  : 'border-yellow-500/40 bg-yellow-500/10 text-yellow-300 hover:bg-yellow-500/20'
              } ${togglingAudit ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <Power className="h-4 w-4" />
              <span className="hidden sm:inline">
                {togglingAudit
                  ? t('logging.toggling')
                  : auditStatus.enabled
                  ? t('logging.disableLogging')
                  : t('logging.enableLogging')}
              </span>
              <span className="sm:hidden">
                {auditStatus.enabled ? t('common:off') : t('common:on')}
              </span>
            </button>
          )}
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value={1}>{t('logging.lastHour', { count: 1 })}</option>
            <option value={6}>{t('logging.lastHours', { count: 6 })}</option>
            <option value={24}>{t('logging.lastHours', { count: 24 })}</option>
            <option value={72}>{t('logging.lastDays', { count: 3 })}</option>
            <option value={168}>{t('logging.lastWeek')}</option>
          </select>
          <button
            onClick={loadData}
            className="btn btn-primary flex items-center gap-2 justify-center touch-manipulation active:scale-95"
          >
            <RefreshCw className="h-4 w-4" />
            <span className="hidden sm:inline">{t('common:refresh')}</span>
          </button>
        </div>
      </div>

      {/* File Access Logs */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <div className="flex flex-col gap-3 mb-4">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-slate-400" />
            <h2 className="text-lg sm:text-xl font-semibold text-white">{t('logging.fileAccessLogs')}</h2>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">{t('logging.allActions')}</option>
              {availableActions.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>
            <select
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">{t('logging.allUsers')}</option>
              {availableUsers.map((user) => (
                <option key={user} value={user}>
                  {user}
                </option>
              ))}
            </select>
          </div>
        </div>

        {fileAccessLogs && fileAccessLogs.logs.length > 0 ? (
          <>
            {/* Desktop Table */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-800/60">
                <thead>
                  <tr className="text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                    <th className="px-4 py-3">{t('logging.timestamp')}</th>
                    <th className="px-4 py-3">{t('logging.user')}</th>
                    <th className="px-4 py-3">{t('logging.action')}</th>
                    <th className="px-4 py-3">{t('logging.file')}</th>
                    <th className="px-4 py-3">{t('logging.size')}</th>
                    <th className="px-4 py-3">{t('logging.duration')}</th>
                    <th className="px-4 py-3">{t('logging.status')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {fileAccessLogs.logs.map((log, index) => (
                    <tr
                      key={index}
                      className="text-sm text-slate-300 hover:bg-slate-800/50 transition"
                    >
                      <td className="px-4 py-3 whitespace-nowrap text-slate-400">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-300">
                          {log.user}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getActionBadgeClass(log.action)}`}>
                          {log.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 max-w-xs truncate" title={log.resource}>
                        {log.resource}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {formatBytes(log.details?.size_bytes)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {log.details?.duration_ms
                          ? `${log.details.duration_ms}ms`
                          : '-'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {log.success ? (
                          <span className="inline-flex items-center text-green-400">
                            <CheckCircle className="h-4 w-4 mr-1" />
                            {t('logging.success')}
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center text-red-400"
                            title={log.error}
                          >
                            <XCircle className="h-4 w-4 mr-1" />
                            {t('logging.failed')}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Card View */}
            <div className="lg:hidden space-y-3">
              {fileAccessLogs.logs.map((log, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                >
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-300">
                        {log.user}
                      </span>
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getActionBadgeClass(log.action)}`}>
                        {log.action}
                      </span>
                    </div>
                    {log.success ? (
                      <CheckCircle className="h-5 w-5 text-green-400 flex-shrink-0" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                    )}
                  </div>

                  <p className="text-sm text-slate-200 break-all mb-2" title={log.resource}>
                    {log.resource}
                  </p>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                    <span>{formatTimestamp(log.timestamp)}</span>
                    {log.details?.size_bytes && (
                      <span>{formatBytes(log.details.size_bytes)}</span>
                    )}
                    {log.details?.duration_ms && (
                      <span>{log.details.duration_ms}ms</span>
                    )}
                  </div>

                  {!log.success && log.error && (
                    <p className="mt-2 text-xs text-red-400">{log.error}</p>
                  )}
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-slate-400">{t('logging.noLogsFound')}</div>
        )}

        {fileAccessLogs && fileAccessLogs.total > fileAccessLogs.logs.length && (
          <div className="mt-4 text-center text-sm text-slate-400">
            {t('logging.showingOfTotal', { shown: fileAccessLogs.logs.length, total: fileAccessLogs.total })}
          </div>
        )}
      </div>
    </div>
  );
};

export default Logging;
