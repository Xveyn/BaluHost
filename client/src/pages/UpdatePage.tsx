/**
 * UpdatePage - System Update Management
 *
 * Allows admins to:
 * - Check for available updates
 * - View changelog and version info
 * - Start and monitor updates
 * - View update history
 * - Configure auto-update settings
 * - Rollback to previous versions
 */
import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-hot-toast';
import {
  Download,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  History,
  Settings,
  Package,
  GitBranch,
  Clock,
  Loader2,
  RotateCcw,
  ArrowRight,
  Zap,
} from 'lucide-react';
import {
  checkForUpdates,
  startUpdate,
  getUpdateProgress,
  getCurrentUpdate,
  rollbackUpdate,
  getUpdateHistory,
  getUpdateConfig,
  updateConfig,
  getStatusInfo,
  formatDuration,
  isUpdateInProgress,
  getChannelInfo,
  type UpdateCheckResponse,
  type UpdateProgressResponse,
  type UpdateHistoryEntry,
  type UpdateConfig,
  type UpdateChannel,
} from '../api/updates';
import UpdateProgress from '../components/updates/UpdateProgress';

type TabId = 'overview' | 'history' | 'settings';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'overview', label: 'Overview', icon: <Package className="h-4 w-4" /> },
  { id: 'history', label: 'History', icon: <History className="h-4 w-4" /> },
  { id: 'settings', label: 'Settings', icon: <Settings className="h-4 w-4" /> },
];

export default function UpdatePage() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(true);
  const [checkLoading, setCheckLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);

  // Data state
  const [checkResult, setCheckResult] = useState<UpdateCheckResponse | null>(null);
  const [currentUpdate, setCurrentUpdate] = useState<UpdateProgressResponse | null>(null);
  const [history, setHistory] = useState<UpdateHistoryEntry[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [config, setConfig] = useState<UpdateConfig | null>(null);

  // Confirmation states
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);

  // Fetch update check
  const fetchCheck = useCallback(async () => {
    setCheckLoading(true);
    try {
      const result = await checkForUpdates();
      setCheckResult(result);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to check for updates');
    } finally {
      setCheckLoading(false);
    }
  }, []);

  // Fetch current update progress
  const fetchCurrentUpdate = useCallback(async () => {
    try {
      const result = await getCurrentUpdate();
      setCurrentUpdate(result);
      return result;
    } catch (err) {
      setCurrentUpdate(null);
      return null;
    }
  }, []);

  // Fetch history
  const fetchHistory = useCallback(async () => {
    try {
      const result = await getUpdateHistory({ page: historyPage, page_size: 10 });
      setHistory(result.updates);
      setHistoryTotal(result.total);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to fetch history');
    }
  }, [historyPage]);

  // Fetch config
  const fetchConfig = useCallback(async () => {
    try {
      const result = await getUpdateConfig();
      setConfig(result);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to fetch config');
    }
  }, []);

  // Initial load
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchCheck(), fetchCurrentUpdate(), fetchConfig()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchCheck, fetchCurrentUpdate, fetchConfig]);

  // Fetch history when tab changes
  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab, fetchHistory]);

  // Poll for update progress when update is running
  useEffect(() => {
    if (!currentUpdate || !isUpdateInProgress(currentUpdate.status)) return;

    const interval = setInterval(async () => {
      try {
        const progress = await getUpdateProgress(currentUpdate.update_id);
        setCurrentUpdate(progress);

        // If update completed or failed, refresh check result
        if (!isUpdateInProgress(progress.status)) {
          await fetchCheck();
          if (progress.status === 'completed') {
            toast.success(`Updated to ${progress.to_version}`);
          }
        }
      } catch (err) {
        // Update might have restarted the service
        console.log('Update progress fetch failed, service may be restarting');
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [currentUpdate, fetchCheck]);

  // Start update
  const handleStartUpdate = async () => {
    setUpdateLoading(true);
    setShowUpdateConfirm(false);
    try {
      const result = await startUpdate();
      if (result.success && result.update_id) {
        toast.success('Update started');
        const progress = await getUpdateProgress(result.update_id);
        setCurrentUpdate(progress);
      } else {
        toast.error(result.message);
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object' && detail.blockers) {
        toast.error(`Update blocked: ${detail.blockers.join(', ')}`);
      } else {
        toast.error(detail || 'Failed to start update');
      }
    } finally {
      setUpdateLoading(false);
    }
  };

  // Rollback
  const handleRollback = async (updateId?: number) => {
    setRollbackLoading(true);
    setShowRollbackConfirm(false);
    try {
      const result = await rollbackUpdate({
        target_update_id: updateId || rollbackTarget || undefined,
      });
      if (result.success) {
        toast.success(`Rolled back to ${result.rolled_back_to}`);
        await fetchCheck();
        await fetchHistory();
        setCurrentUpdate(null);
      } else {
        toast.error(result.message);
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Rollback failed');
    } finally {
      setRollbackLoading(false);
      setRollbackTarget(null);
    }
  };

  // Update config
  const handleConfigChange = async (key: keyof UpdateConfig, value: any) => {
    if (!config) return;
    setConfigLoading(true);
    try {
      const updated = await updateConfig({ [key]: value });
      setConfig(updated);
      toast.success('Settings saved');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setConfigLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Download className="h-7 w-7 text-sky-500" />
            System Updates
          </h1>
          <p className="text-slate-400 mt-1">
            Manage BaluHost updates and version control
          </p>
        </div>
        <button
          onClick={fetchCheck}
          disabled={checkLoading}
          className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${checkLoading ? 'animate-spin' : ''}`} />
          Check for Updates
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-800 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
              activeTab === tab.id
                ? 'bg-slate-700 text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Current Update Progress */}
          {currentUpdate && isUpdateInProgress(currentUpdate.status) && (
            <UpdateProgress
              progress={currentUpdate}
              onRollback={() => setShowRollbackConfirm(true)}
              rollbackLoading={rollbackLoading}
            />
          )}

          {/* Version Info Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Current Version */}
            <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
              <div className="flex items-center gap-2 mb-4">
                <Package className="h-5 w-5 text-slate-400" />
                <h3 className="font-medium text-white">Current Version</h3>
              </div>
              {checkResult && (
                <div className="space-y-3">
                  <div className="text-3xl font-bold text-white">
                    v{checkResult.current_version.version}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <GitBranch className="h-4 w-4" />
                    <span className="font-mono">
                      {checkResult.current_version.commit_short}
                    </span>
                    {checkResult.current_version.tag && (
                      <span className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                        {checkResult.current_version.tag}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <span className={getChannelInfo(checkResult.channel).color}>
                      {getChannelInfo(checkResult.channel).label} Channel
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Available Update */}
            <div
              className={`bg-slate-800 rounded-lg p-5 border ${
                checkResult?.update_available
                  ? 'border-sky-500/50 bg-sky-500/5'
                  : 'border-slate-700'
              }`}
            >
              <div className="flex items-center gap-2 mb-4">
                {checkResult?.update_available ? (
                  <Zap className="h-5 w-5 text-sky-400" />
                ) : (
                  <CheckCircle className="h-5 w-5 text-emerald-400" />
                )}
                <h3 className="font-medium text-white">
                  {checkResult?.update_available ? 'Update Available' : 'Up to Date'}
                </h3>
              </div>
              {checkResult?.update_available && checkResult.latest_version ? (
                <div className="space-y-3">
                  <div className="text-3xl font-bold text-sky-400">
                    v{checkResult.latest_version.version}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <GitBranch className="h-4 w-4" />
                    <span className="font-mono">
                      {checkResult.latest_version.commit_short}
                    </span>
                  </div>
                  {checkResult.last_checked && (
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <Clock className="h-3 w-3" />
                      Last checked: {new Date(checkResult.last_checked).toLocaleString()}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-slate-400">
                  You're running the latest version.
                </p>
              )}
            </div>
          </div>

          {/* Blockers Warning */}
          {checkResult?.blockers && checkResult.blockers.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5" />
                <div>
                  <h4 className="font-medium text-amber-400">Update Blocked</h4>
                  <ul className="mt-2 space-y-1 text-sm text-slate-300">
                    {checkResult.blockers.map((blocker, i) => (
                      <li key={i}>• {blocker}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Changelog */}
          {checkResult?.update_available && checkResult.changelog.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
              <h3 className="font-medium text-white mb-4">Changelog</h3>
              <div className="space-y-4">
                {checkResult.changelog.map((entry, i) => (
                  <div key={i} className="border-l-2 border-sky-500/50 pl-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-medium text-white">v{entry.version}</span>
                      {entry.is_prerelease && (
                        <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                          Pre-release
                        </span>
                      )}
                    </div>
                    {entry.changes.length > 0 && (
                      <ul className="space-y-1 text-sm text-slate-300">
                        {entry.changes.map((change, j) => (
                          <li key={j}>• {change}</li>
                        ))}
                      </ul>
                    )}
                    {entry.breaking_changes.length > 0 && (
                      <div className="mt-2">
                        <span className="text-rose-400 text-sm font-medium">
                          Breaking Changes:
                        </span>
                        <ul className="space-y-1 text-sm text-rose-300">
                          {entry.breaking_changes.map((change, j) => (
                            <li key={j}>• {change}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Update Button */}
          {checkResult?.update_available && (
            <div className="flex justify-end gap-3">
              {!showUpdateConfirm ? (
                <button
                  onClick={() => setShowUpdateConfirm(true)}
                  disabled={!checkResult.can_update || updateLoading || !!currentUpdate}
                  className="flex items-center gap-2 px-6 py-3 bg-sky-600 hover:bg-sky-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors font-medium"
                >
                  <Download className="h-5 w-5" />
                  Update to v{checkResult.latest_version?.version}
                </button>
              ) : (
                <div className="flex items-center gap-3 p-3 bg-slate-700 rounded-lg">
                  <span className="text-sm text-slate-300">Confirm update?</span>
                  <button
                    onClick={handleStartUpdate}
                    disabled={updateLoading}
                    className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded text-sm"
                  >
                    {updateLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      'Yes, Update'
                    )}
                  </button>
                  <button
                    onClick={() => setShowUpdateConfirm(false)}
                    className="px-4 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-sm"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/50">
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">
                  Version
                </th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">
                  Date
                </th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">
                  Duration
                </th>
                <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    No update history
                  </td>
                </tr>
              ) : (
                history.map((entry) => {
                  const statusInfo = getStatusInfo(entry.status);
                  return (
                    <tr
                      key={entry.id}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-slate-400 font-mono text-sm">
                            {entry.from_version}
                          </span>
                          <ArrowRight className="h-3 w-3 text-slate-500" />
                          <span className="text-white font-mono text-sm">
                            {entry.to_version}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs ${statusInfo.bgColor} ${statusInfo.color}`}
                        >
                          {statusInfo.icon} {statusInfo.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-400">
                        {new Date(entry.started_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-400">
                        {formatDuration(entry.duration_seconds)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {entry.can_rollback && entry.status === 'completed' && (
                          <button
                            onClick={() => {
                              setRollbackTarget(entry.id);
                              setShowRollbackConfirm(true);
                            }}
                            className="text-amber-400 hover:text-amber-300 text-sm"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          {/* Pagination */}
          {historyTotal > 10 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700">
              <span className="text-sm text-slate-400">
                Page {historyPage} of {Math.ceil(historyTotal / 10)}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                  disabled={historyPage === 1}
                  className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white rounded text-sm"
                >
                  Previous
                </button>
                <button
                  onClick={() => setHistoryPage((p) => p + 1)}
                  disabled={historyPage >= Math.ceil(historyTotal / 10)}
                  className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white rounded text-sm"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'settings' && config && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700 space-y-6">
          {/* Auto-Check */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">Automatic Update Checks</h3>
              <p className="text-sm text-slate-400">
                Periodically check for new versions
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_check_enabled}
                onChange={(e) =>
                  handleConfigChange('auto_check_enabled', e.target.checked)
                }
                disabled={configLoading}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-600"></div>
            </label>
          </div>

          {/* Check Interval */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">Check Interval</h3>
              <p className="text-sm text-slate-400">Hours between automatic checks</p>
            </div>
            <select
              value={config.check_interval_hours}
              onChange={(e) =>
                handleConfigChange('check_interval_hours', parseInt(e.target.value))
              }
              disabled={configLoading || !config.auto_check_enabled}
              className="bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm"
            >
              <option value={6}>Every 6 hours</option>
              <option value={12}>Every 12 hours</option>
              <option value={24}>Every 24 hours</option>
              <option value={48}>Every 2 days</option>
              <option value={168}>Every week</option>
            </select>
          </div>

          {/* Update Channel */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">Update Channel</h3>
              <p className="text-sm text-slate-400">
                {getChannelInfo(config.channel as UpdateChannel).description}
              </p>
            </div>
            <select
              value={config.channel}
              onChange={(e) =>
                handleConfigChange('channel', e.target.value as UpdateChannel)
              }
              disabled={configLoading}
              className="bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm"
            >
              <option value="stable">Stable</option>
              <option value="beta">Beta</option>
            </select>
          </div>

          {/* Auto Backup */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">Backup Before Update</h3>
              <p className="text-sm text-slate-400">
                Create database backup before installing updates
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_backup_before_update}
                onChange={(e) =>
                  handleConfigChange('auto_backup_before_update', e.target.checked)
                }
                disabled={configLoading}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-600"></div>
            </label>
          </div>

          {/* Require Healthy Services */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-white">Require Healthy Services</h3>
              <p className="text-sm text-slate-400">
                Only allow updates when all services are healthy
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={config.require_healthy_services}
                onChange={(e) =>
                  handleConfigChange('require_healthy_services', e.target.checked)
                }
                disabled={configLoading}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-600"></div>
            </label>
          </div>

          {/* Last Check Info */}
          {config.last_check_at && (
            <div className="pt-4 border-t border-slate-700">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Clock className="h-4 w-4" />
                <span>
                  Last checked: {new Date(config.last_check_at).toLocaleString()}
                </span>
                {config.last_available_version && (
                  <span className="text-sky-400">
                    (v{config.last_available_version} available)
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Rollback Confirmation Modal */}
      {showRollbackConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4 border border-slate-700">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="h-6 w-6 text-amber-400" />
              <h3 className="text-lg font-medium text-white">Confirm Rollback</h3>
            </div>
            <p className="text-slate-300 mb-6">
              Are you sure you want to rollback? This will restore the previous version
              and may require a service restart.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowRollbackConfirm(false);
                  setRollbackTarget(null);
                }}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => handleRollback()}
                disabled={rollbackLoading}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg"
              >
                {rollbackLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )}
                Rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
