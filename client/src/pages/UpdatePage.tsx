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
import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'react-hot-toast';
import {
  Download,
  RefreshCw,
  AlertTriangle,
  History,
  Settings,
  Package,
  GitCommit,
  Loader2,
  RotateCcw,
} from 'lucide-react';
import {
  checkForUpdates,
  startUpdate,
  startDevUpdate,
  getUpdateProgress,
  getCurrentUpdate,
  rollbackUpdate,
  cancelUpdate,
  getUpdateConfig,
  updateConfig,
  getReleaseNotes,
  getAllReleases,
  getVersionHistory,
  isUpdateInProgress,
  type UpdateCheckResponse,
  type UpdateProgressResponse,
  type UpdateConfig,
  type ReleaseNotesResponse,
  type ReleaseInfo,
  type VersionHistoryResponse,
} from '../api/updates';
import { handleApiError } from '../lib/errorHandling';
import UpdateOverviewTab from '../components/updates/UpdateOverviewTab';
import UpdateHistoryTab from '../components/updates/UpdateHistoryTab';
import UpdateSettingsTab from '../components/updates/UpdateSettingsTab';

const VersionsTab = lazy(() => import('../components/updates/VersionsTab'));

type TabId = 'overview' | 'history' | 'settings' | 'versions';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'overview', label: 'tabs.overview', icon: <Package className="h-4 w-4" /> },
  { id: 'history', label: 'tabs.history', icon: <History className="h-4 w-4" /> },
  { id: 'settings', label: 'tabs.settings', icon: <Settings className="h-4 w-4" /> },
  { id: 'versions', label: 'tabs.versions', icon: <GitCommit className="h-4 w-4" /> },
];

export default function UpdatePage() {
  const { t } = useTranslation(['updates', 'common']);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(true);
  const [checkLoading, setCheckLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [cancelLoading, setCancelLoading] = useState(false);

  // Data state
  const [checkResult, setCheckResult] = useState<UpdateCheckResponse | null>(null);
  const [currentUpdate, setCurrentUpdate] = useState<UpdateProgressResponse | null>(null);
  const [config, setConfig] = useState<UpdateConfig | null>(null);
  const [releaseNotes, setReleaseNotes] = useState<ReleaseNotesResponse | null>(null);
  const [releases, setReleases] = useState<ReleaseInfo[]>([]);
  const [releasesLoading, setReleasesLoading] = useState(false);
  const [versionHistory, setVersionHistory] = useState<VersionHistoryResponse | null>(null);
  const [versionHistoryLoading, setVersionHistoryLoading] = useState(false);

  // Confirmation states
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);
  const [showDevUpdateConfirm, setShowDevUpdateConfirm] = useState(false);
  const [devUpdateLoading, setDevUpdateLoading] = useState(false);
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);

  // Fetch update check
  const fetchCheck = useCallback(async () => {
    setCheckLoading(true);
    try {
      const result = await checkForUpdates();
      setCheckResult(result);
    } catch (err: unknown) {
      handleApiError(err, t('common:toast.checkFailed'));
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
    } catch {
      setCurrentUpdate(null);
      return null;
    }
  }, []);

  // Fetch release notes
  const fetchReleaseNotes = useCallback(async () => {
    try {
      const result = await getReleaseNotes();
      setReleaseNotes(result);
    } catch {
      // Non-critical, don't show error toast
    }
  }, []);

  // Fetch config
  const fetchConfig = useCallback(async () => {
    try {
      const result = await getUpdateConfig();
      setConfig(result);
    } catch (err: unknown) {
      handleApiError(err, t('common:toast.configFailed'));
    }
  }, []);

  // Fetch releases
  const fetchReleases = useCallback(async () => {
    setReleasesLoading(true);
    try {
      const result = await getAllReleases();
      setReleases(result.releases);
    } catch {
      // Non-critical, don't show error toast
    } finally {
      setReleasesLoading(false);
    }
  }, []);

  // Fetch version history
  const fetchVersionHistory = useCallback(async () => {
    setVersionHistoryLoading(true);
    try {
      const result = await getVersionHistory();
      setVersionHistory(result);
    } catch {
      // Non-critical, don't show error toast
    } finally {
      setVersionHistoryLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchCheck(), fetchCurrentUpdate(), fetchConfig(), fetchReleaseNotes()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchCheck, fetchCurrentUpdate, fetchConfig, fetchReleaseNotes]);

  // Fetch history tab data when tab changes
  useEffect(() => {
    if (activeTab === 'history') {
      fetchReleases();
      fetchVersionHistory();
    }
  }, [activeTab]);

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
            toast.success(t('common:toast.updateCompleted', { version: progress.to_version }));
          }
        }
      } catch {
        // Update might have restarted the service
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
        toast.success(t('common:toast.updateStarted'));
        const progress = await getUpdateProgress(result.update_id);
        setCurrentUpdate(progress);
      } else {
        toast.error(result.message);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (typeof detail === 'object' && detail !== null && 'blockers' in detail) {
        const blockers = (detail as { blockers: string[] }).blockers;
        toast.error(t('blockers.updateBlocked', { blockers: blockers.join(', ') }));
      } else {
        handleApiError(err, t('common:toast.updateFailed'));
      }
    } finally {
      setUpdateLoading(false);
    }
  };

  // Start dev update
  const handleStartDevUpdate = async () => {
    setDevUpdateLoading(true);
    setShowDevUpdateConfirm(false);
    try {
      const result = await startDevUpdate();
      if (result.success && result.update_id) {
        toast.success(t('toast.devUpdateStarted'));
        const progress = await getUpdateProgress(result.update_id);
        setCurrentUpdate(progress);
      } else {
        toast.error(result.message);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (typeof detail === 'object' && detail !== null && 'blockers' in detail) {
        const blockers = (detail as { blockers: string[] }).blockers;
        toast.error(t('blockers.updateBlocked', { blockers: blockers.join(', ') }));
      } else {
        handleApiError(err, t('toast.updateFailed'));
      }
    } finally {
      setDevUpdateLoading(false);
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
        toast.success(t('common:toast.rollbackSuccess', { version: result.rolled_back_to }));
        await fetchCheck();
        setCurrentUpdate(null);
      } else {
        toast.error(result.message);
      }
    } catch (err: unknown) {
      handleApiError(err, t('common:toast.rollbackFailed'));
    } finally {
      setRollbackLoading(false);
      setRollbackTarget(null);
    }
  };

  // Cancel update
  const handleCancel = async () => {
    if (!currentUpdate) return;
    setCancelLoading(true);
    try {
      const result = await cancelUpdate(currentUpdate.update_id);
      if (result.success) {
        toast.success(t('toast.updateCancelled'));
        setCurrentUpdate(null);
        await fetchCheck();
      } else {
        toast.error(result.message);
      }
    } catch (err: unknown) {
      handleApiError(err, t('toast.cancelFailed'));
    } finally {
      setCancelLoading(false);
    }
  };

  // Update config
  const handleConfigChange = async (key: keyof UpdateConfig, value: UpdateConfig[keyof UpdateConfig]) => {
    if (!config) return;
    setConfigLoading(true);
    try {
      const updated = await updateConfig({ [key]: value });
      setConfig(updated);
      toast.success(t('common:toast.settingsSaved'));
    } catch (err: unknown) {
      handleApiError(err, t('common:toast.settingsFailed'));
    } finally {
      setConfigLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-3">
            <Download className="h-7 w-7 text-blue-500" />
            {t('title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {t('description')}
          </p>
        </div>
        <button
          onClick={fetchCheck}
          disabled={checkLoading}
          className="flex items-center gap-2 rounded-lg px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${checkLoading ? 'animate-spin' : ''}`} />
          {t('buttons.checkForUpdates')}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-3 overflow-x-auto scrollbar-none">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              activeTab === tab.id
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            {tab.icon}
            {t(tab.label)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <UpdateOverviewTab
          t={t}
          checkResult={checkResult}
          currentUpdate={currentUpdate}
          releaseNotes={releaseNotes}
          updateLoading={updateLoading}
          rollbackLoading={rollbackLoading}
          cancelLoading={cancelLoading}
          devUpdateLoading={devUpdateLoading}
          showUpdateConfirm={showUpdateConfirm}
          showDevUpdateConfirm={showDevUpdateConfirm}
          onSetShowUpdateConfirm={setShowUpdateConfirm}
          onSetShowDevUpdateConfirm={setShowDevUpdateConfirm}
          onSetShowRollbackConfirm={setShowRollbackConfirm}
          onStartUpdate={handleStartUpdate}
          onStartDevUpdate={handleStartDevUpdate}
          onCancel={handleCancel}
        />
      )}

      {activeTab === 'history' && (
        <UpdateHistoryTab
          t={t}
          releases={releases}
          releasesLoading={releasesLoading}
          versionHistory={versionHistory}
          versionHistoryLoading={versionHistoryLoading}
        />
      )}

      {activeTab === 'settings' && config && (
        <UpdateSettingsTab
          t={t}
          config={config}
          configLoading={configLoading}
          onConfigChange={handleConfigChange}
        />
      )}

      {activeTab === 'versions' && (
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          }
        >
          <VersionsTab />
        </Suspense>
      )}

      {/* Rollback Confirmation Modal */}
      {showRollbackConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4 border border-slate-700">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="h-6 w-6 text-amber-400" />
              <h3 className="text-lg font-medium text-white">{t('rollback.title')}</h3>
            </div>
            <p className="text-slate-300 mb-6">
              {t('rollback.description')}
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowRollbackConfirm(false);
                  setRollbackTarget(null);
                }}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-all touch-manipulation active:scale-95"
              >
                {t('common:cancel')}
              </button>
              <button
                onClick={() => handleRollback()}
                disabled={rollbackLoading}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-all touch-manipulation active:scale-95"
              >
                {rollbackLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )}
                {t('buttons.rollback')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
