/**
 * VCL Settings Component (Admin)
 * Global VCL settings, per-user limits, stats dashboard, maintenance
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  HardDrive,
  Users,
  TrendingUp,
  RefreshCw,
  Trash2,
  AlertCircle,
  Check,
  Star,
  Clock,
  Database,
  FolderOpen,
  Search,
  ArrowRight,
  AlertTriangle,
} from 'lucide-react';
import {
  getAdminOverview,
  getAdminUsers,
  getStorageInfo,
  updateUserSettingsAdmin,
  triggerCleanup,
  getReconciliationPreview,
  applyReconciliation,
  formatBytes,
} from '../../api/vcl';
import { formatNumber } from '../../lib/formatters';
import { ByteSizeInput } from '../ui/ByteSizeInput';
import type {
  AdminVCLOverview,
  UserVCLStats,
  VCLSettingsUpdate,
  VCLStorageInfo,
  ReconciliationPreview,
} from '../../types/vcl';

export default function VCLSettings() {
  const [overview, setOverview] = useState<AdminVCLOverview | null>(null);
  const [storageInfo, setStorageInfo] = useState<VCLStorageInfo | null>(null);
  const [users, setUsers] = useState<UserVCLStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Edit modal state
  const [editingUser, setEditingUser] = useState<UserVCLStats | null>(null);
  const [editForm, setEditForm] = useState<VCLSettingsUpdate>({});
  const { t } = useTranslation('admin');

  // Reconciliation state
  const [reconPreview, setReconPreview] = useState<ReconciliationPreview | null>(null);
  const [reconLoading, setReconLoading] = useState(false);
  const [forceOverQuota, setForceOverQuota] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [overviewData, usersData, storageData] = await Promise.all([
        getAdminOverview(),
        getAdminUsers(100, 0),
        getStorageInfo().catch(() => null),
      ]);
      setOverview(overviewData);
      setUsers(usersData?.users || []);
      setStorageInfo(storageData);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || t('vcl.errors.loadFailed'));
      // Set empty arrays on error
      setUsers([]);
      setOverview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async (dryRun: boolean = false) => {
    if (!dryRun && !confirm(t('vcl.maintenance.confirmCleanup'))) return;

    try {
      setActionLoading(true);
      setError(null);
      const result = await triggerCleanup({ dry_run: dryRun });
      setSuccessMessage(
        t(dryRun ? 'vcl.cleanup.dryRunResult' : 'vcl.cleanup.result', { versions: result.deleted_versions, freed: formatBytes(result.freed_bytes) })
      );
      setTimeout(() => setSuccessMessage(null), 5000);
      if (!dryRun) loadData(); // Reload stats
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || t('vcl.errors.cleanupFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleScanMismatches = async () => {
    try {
      setReconLoading(true);
      setError(null);
      const preview = await getReconciliationPreview({});
      setReconPreview(preview);
      if (preview.total_mismatches === 0) {
        setSuccessMessage('No ownership mismatches found');
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to scan for mismatches');
    } finally {
      setReconLoading(false);
    }
  };

  const handleApplyReconciliation = async () => {
    if (!confirm('Apply ownership reconciliation? This will update version ownership to match file ownership.')) return;
    try {
      setReconLoading(true);
      setError(null);
      const result = await applyReconciliation({ force_over_quota: forceOverQuota });
      setSuccessMessage(result.message);
      setTimeout(() => setSuccessMessage(null), 5000);
      setReconPreview(null);
      loadData();
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to apply reconciliation');
    } finally {
      setReconLoading(false);
    }
  };

  const handleEditUser = (user: UserVCLStats) => {
    setEditingUser(user);
    setEditForm({
      max_size_bytes: user.max_size_bytes,
      is_enabled: user.is_enabled,
    });
  };

  const handleSaveUserSettings = async () => {
    if (!editingUser) return;

    try {
      setActionLoading(true);
      setError(null);
      await updateUserSettingsAdmin(editingUser.user_id, editForm);
      setSuccessMessage(t('vcl.settingsUpdated', { username: editingUser.username }));
      setTimeout(() => setSuccessMessage(null), 3000);
      setEditingUser(null);
      loadData(); // Reload
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || t('vcl.errors.updateFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
      </div>
    );
  }

  if (!overview) return null;

  const compressionRatio = overview.compression_ratio;
  const totalSavings = overview.total_savings_bytes;
  const savingsPercent = overview.total_size_bytes > 0
    ? ((totalSavings / overview.total_size_bytes) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Messages */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}
      {successMessage && (
        <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2 text-green-400">
          <Check className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">{successMessage}</span>
        </div>
      )}

      {/* VCL Storage Info */}
      {storageInfo && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-sky-400" />
            {t('vcl.storageInfo.title', 'Storage Location')}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-slate-400">{t('vcl.storageInfo.path', 'Storage Path')}</p>
              <p className="text-white font-semibold mt-1 truncate" title={storageInfo.storage_path}>
                {storageInfo.storage_path}
              </p>
              {storageInfo.is_custom_path && (
                <span className="mt-1 inline-block px-2 py-0.5 rounded-full text-[10px] font-medium bg-violet-500/20 text-violet-300">
                  Custom Path
                </span>
              )}
            </div>
            <div>
              <p className="text-slate-400">{t('vcl.storageInfo.blobCount', 'Blob Count')}</p>
              <p className="text-white font-semibold mt-1">{storageInfo.blob_count.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('vcl.storageInfo.compressedSize', 'Compressed Size')}</p>
              <p className="text-white font-semibold mt-1">{formatBytes(storageInfo.total_compressed_bytes)}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('vcl.storageInfo.diskUsage', 'Disk Usage')}</p>
              <p className="text-white font-semibold mt-1">
                {formatNumber(storageInfo.disk_used_percent, 1)}%
              </p>
              <div className="h-1.5 w-full mt-1.5 overflow-hidden rounded-full bg-slate-800 max-w-[120px]">
                <div
                  className={`h-full rounded-full transition-all ${
                    storageInfo.disk_used_percent >= 90 ? 'bg-red-500' : storageInfo.disk_used_percent >= 70 ? 'bg-amber-500' : 'bg-sky-500'
                  }`}
                  style={{ width: `${Math.min(storageInfo.disk_used_percent, 100)}%` }}
                />
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {formatBytes(storageInfo.disk_available_bytes)} {t('vcl.storageInfo.free', 'free')} / {formatBytes(storageInfo.disk_total_bytes)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">{t('vcl.stats.totalVersions')}</p>
              <p className="text-2xl font-bold text-white mt-1">{overview.total_versions.toLocaleString()}</p>
            </div>
            <Clock className="w-10 h-10 text-sky-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">{t('vcl.stats.storageUsed')}</p>
              <p className="text-2xl font-bold text-white mt-1">{formatBytes(overview.total_compressed_bytes)}</p>
              <p className="text-xs text-slate-500 mt-1">{formatBytes(overview.total_size_bytes)} {t('vcl.stats.original')}</p>
            </div>
            <HardDrive className="w-10 h-10 text-violet-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">{t('vcl.stats.totalSavings')}</p>
              <p className="text-2xl font-bold text-white mt-1">{formatNumber(savingsPercent, 1)}%</p>
              <p className="text-xs text-slate-500 mt-1">{formatBytes(totalSavings)} {t('vcl.stats.saved')}</p>
            </div>
            <TrendingUp className="w-10 h-10 text-green-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">{t('vcl.stats.activeUsers')}</p>
              <p className="text-2xl font-bold text-white mt-1">{overview.total_users}</p>
              <p className="text-xs text-slate-500 mt-1">{overview.cached_versions_count} {t('vcl.stats.cached')}</p>
            </div>
            <Users className="w-10 h-10 text-amber-400 opacity-50" />
          </div>
        </div>
      </div>

      {/* Detailed Stats */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Database className="w-5 h-5 text-sky-400" />
          {t('vcl.storageDetails.title')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.compressionRatio')}</p>
            <p className="text-white font-semibold mt-1">{formatNumber(compressionRatio, 2)}x</p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.compressionSavings')}</p>
            <p className="text-white font-semibold mt-1">{formatBytes(overview.compression_savings_bytes)}</p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.dedupSavings')}</p>
            <p className="text-white font-semibold mt-1">{formatBytes(overview.deduplication_savings_bytes)}</p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.uniqueBlobs')}</p>
            <p className="text-white font-semibold mt-1">{overview.unique_blobs} / {overview.total_blobs}</p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.priorityVersions')}</p>
            <p className="text-white font-semibold mt-1 flex items-center gap-1">
              <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
              {overview.priority_count}
            </p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.lastCleanup')}</p>
            <p className="text-white font-semibold mt-1">
              {overview.last_cleanup_at ? new Date(overview.last_cleanup_at).toLocaleDateString() : t('vcl.storageDetails.never')}
            </p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.lastPriorityMode')}</p>
            <p className="text-white font-semibold mt-1">
              {overview.last_priority_mode_at ? new Date(overview.last_priority_mode_at).toLocaleDateString() : t('vcl.storageDetails.never')}
            </p>
          </div>
          <div>
            <p className="text-slate-400">{t('vcl.storageDetails.updated')}</p>
            <p className="text-white font-semibold mt-1">
              {overview.updated_at ? new Date(overview.updated_at).toLocaleTimeString() : t('common.na')}
            </p>
          </div>
        </div>
      </div>

      {/* Maintenance Actions */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-sky-400" />
          {t('vcl.maintenance.title')}
        </h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => handleCleanup(true)}
            disabled={actionLoading}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            {t('vcl.maintenance.dryRunCleanup')}
          </button>
          <button
            onClick={() => handleCleanup(false)}
            disabled={actionLoading}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            {t('vcl.maintenance.triggerCleanup')}
          </button>
          <button
            onClick={loadData}
            disabled={actionLoading}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
            {t('vcl.maintenance.refreshStats')}
          </button>
        </div>
      </div>

      {/* Ownership Reconciliation */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-sky-400" />
          Ownership Reconciliation
        </h3>
        <p className="text-sm text-slate-400 mb-4">
          Scan for version ownership mismatches (e.g. after file transfers) and fix them.
        </p>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <button
            onClick={handleScanMismatches}
            disabled={reconLoading}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Search className={`w-4 h-4 ${reconLoading ? 'animate-spin' : ''}`} />
            Scan for Mismatches
          </button>
          {reconPreview && reconPreview.total_mismatches > 0 && (
            <>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceOverQuota}
                  onChange={(e) => setForceOverQuota(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-700 bg-slate-800"
                />
                Force even if quota exceeded
              </label>
              <button
                onClick={handleApplyReconciliation}
                disabled={reconLoading}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                <Check className="w-4 h-4" />
                Apply ({reconPreview.total_mismatches} versions)
              </button>
            </>
          )}
        </div>

        {reconPreview && reconPreview.total_mismatches > 0 && (
          <div className="space-y-4">
            {/* Affected Users Summary */}
            {reconPreview.affected_users.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-slate-300">Quota Impact</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {reconPreview.affected_users.map((u) => (
                    <div
                      key={u.user_id}
                      className={`p-3 rounded-lg border text-sm ${
                        u.would_exceed_quota
                          ? 'border-amber-500/30 bg-amber-500/10'
                          : 'border-slate-800 bg-slate-800/50'
                      }`}
                    >
                      <span className="font-medium text-white">{u.username}</span>
                      <span className="text-slate-400 ml-2">
                        {u.quota_delta > 0 ? '+' : ''}{formatBytes(Math.abs(u.quota_delta))}
                      </span>
                      {u.would_exceed_quota && (
                        <span className="ml-2 text-amber-400 text-xs flex items-center gap-1 inline-flex">
                          <AlertTriangle className="w-3 h-3" /> exceeds quota
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Mismatch Table */}
            <div className="overflow-x-auto max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-left border-b border-slate-800">
                    <th className="pb-2 text-slate-400 font-medium">File</th>
                    <th className="pb-2 text-slate-400 font-medium">Version</th>
                    <th className="pb-2 text-slate-400 font-medium">Current Owner</th>
                    <th className="pb-2 text-slate-400 font-medium"></th>
                    <th className="pb-2 text-slate-400 font-medium">File Owner</th>
                    <th className="pb-2 text-slate-400 font-medium">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {reconPreview.mismatches.slice(0, 100).map((m) => (
                    <tr key={m.version_id} className="border-b border-slate-800/30">
                      <td className="py-1.5 text-slate-300 max-w-[200px] truncate" title={m.file_path}>
                        {m.file_path.split('/').pop()}
                      </td>
                      <td className="py-1.5 text-slate-400">v{m.version_number}</td>
                      <td className="py-1.5 text-red-300">{m.current_version_username}</td>
                      <td className="py-1.5 text-slate-500"><ArrowRight className="w-3 h-3" /></td>
                      <td className="py-1.5 text-green-300">{m.current_file_owner_username}</td>
                      <td className="py-1.5 text-slate-400">{formatBytes(m.compressed_size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {reconPreview.total_mismatches > 100 && (
                <p className="text-xs text-slate-500 mt-2">
                  Showing 100 of {reconPreview.total_mismatches} mismatches
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* User Limits Table */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Users className="w-5 h-5 text-sky-400" />
          {t('vcl.userQuotas.title')}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-800">
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.user')}</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.maxSize')}</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.used')}</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.usage')}</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.versions')}</th>
                <th className="pb-3 text-slate-400 font-medium">Mode</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.status')}</th>
                <th className="pb-3 text-slate-400 font-medium">{t('vcl.userQuotas.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {users && users.length > 0 ? users.map((user) => {
                const usagePercent = user.usage_percent;
                const isWarning = usagePercent >= 80;
                const isCritical = usagePercent >= 95;

                return (
                  <tr key={user.user_id} className="border-b border-slate-800/50">
                    <td className="py-3 text-white font-medium">{user.username}</td>
                    <td className="py-3 text-slate-300">{formatBytes(user.max_size_bytes)}</td>
                    <td className="py-3 text-slate-300">{formatBytes(user.current_usage_bytes)}</td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden max-w-[100px]">
                          <div
                            className={`h-full transition-all ${
                              isCritical ? 'bg-red-500' : isWarning ? 'bg-amber-500' : 'bg-sky-500'
                            }`}
                            style={{ width: `${Math.min(usagePercent, 100)}%` }}
                          />
                        </div>
                        <span className={`${isCritical ? 'text-red-400' : isWarning ? 'text-amber-400' : 'text-slate-300'}`}>
                          {formatNumber(usagePercent, 1)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-3 text-slate-300">{user.total_versions}</td>
                    <td className="py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        user.vcl_mode === 'manual'
                          ? 'bg-violet-500/20 text-violet-300'
                          : 'bg-sky-500/20 text-sky-300'
                      }`}>
                        {user.vcl_mode === 'manual' ? 'Manual' : 'Auto'}
                      </span>
                    </td>
                    <td className="py-3">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                          user.is_enabled
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}
                      >
                        {user.is_enabled ? t('common.enabled') : t('common.disabled')}
                      </span>
                    </td>
                    <td className="py-3">
                      <button
                        onClick={() => handleEditUser(user)}
                        className="text-sky-400 hover:text-sky-300 transition-colors"
                      >
                        {t('common.edit')}
                      </button>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {t('vcl.userQuotas.noUsers')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit User Modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-slate-900 rounded-xl shadow-2xl border border-slate-800 w-full max-w-md">
            <div className="p-6 border-b border-slate-800">
              <h3 className="text-lg font-semibold text-white">
                {t('vcl.editModal.title', { username: editingUser.username })}
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('vcl.editModal.maxSizeLabel')}
                </label>
                <ByteSizeInput
                  value={editForm.max_size_bytes || 0}
                  onChange={(bytes) => setEditForm({ ...editForm, max_size_bytes: bytes })}
                />
              </div>
              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editForm.is_enabled ?? true}
                    onChange={(e) =>
                      setEditForm({ ...editForm, is_enabled: e.target.checked })
                    }
                    className="w-4 h-4 rounded border-slate-700 bg-slate-800"
                  />
                  <span className="text-sm text-slate-300">{t('vcl.editModal.enableVcl')}</span>
                </label>
              </div>
            </div>
            <div className="p-6 border-t border-slate-800 flex justify-end gap-3">
              <button
                onClick={() => setEditingUser(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSaveUserSettings}
                disabled={actionLoading}
                className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
