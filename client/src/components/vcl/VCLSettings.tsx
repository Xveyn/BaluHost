/**
 * VCL Settings Component (Admin)
 * Global VCL settings, per-user limits, stats dashboard, maintenance
 */

import { useState, useEffect } from 'react';
import {
  HardDrive,
  Users,
  Archive,
  TrendingUp,
  RefreshCw,
  Download,
  Trash2,
  AlertCircle,
  Check,
  Star,
  Clock,
  Database,
} from 'lucide-react';
import {
  getAdminOverview,
  getAdminUsers,
  updateUserSettingsAdmin,
  triggerCleanup,
  formatBytes,
} from '../../api/vcl';
import type { AdminVCLOverview, UserVCLStats, VCLSettingsUpdate } from '../../types/vcl';

export default function VCLSettings() {
  const [overview, setOverview] = useState<AdminVCLOverview | null>(null);
  const [users, setUsers] = useState<UserVCLStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Edit modal state
  const [editingUser, setEditingUser] = useState<UserVCLStats | null>(null);
  const [editForm, setEditForm] = useState<VCLSettingsUpdate>({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [overviewData, usersData] = await Promise.all([
        getAdminOverview(),
        getAdminUsers(100, 0),
      ]);
      setOverview(overviewData);
      setUsers(usersData?.users || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load VCL data');
      // Set empty arrays on error
      setUsers([]);
      setOverview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async (dryRun: boolean = false) => {
    if (!dryRun && !confirm('Trigger cleanup for all users exceeding quota?')) return;

    try {
      setActionLoading(true);
      setError(null);
      const result = await triggerCleanup({ dry_run: dryRun });
      setSuccessMessage(
        `${dryRun ? 'Dry run: Would delete' : 'Deleted'} ${result.deleted_versions} versions, freed ${formatBytes(result.freed_bytes)}`
      );
      setTimeout(() => setSuccessMessage(null), 5000);
      if (!dryRun) loadData(); // Reload stats
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to trigger cleanup');
    } finally {
      setActionLoading(false);
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
      setSuccessMessage(`Updated settings for ${editingUser.username}`);
      setTimeout(() => setSuccessMessage(null), 3000);
      setEditingUser(null);
      loadData(); // Reload
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update settings');
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

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Total Versions</p>
              <p className="text-2xl font-bold text-white mt-1">{overview.total_versions.toLocaleString()}</p>
            </div>
            <Clock className="w-10 h-10 text-sky-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Storage Used</p>
              <p className="text-2xl font-bold text-white mt-1">{formatBytes(overview.total_compressed_bytes)}</p>
              <p className="text-xs text-slate-500 mt-1">{formatBytes(overview.total_size_bytes)} original</p>
            </div>
            <HardDrive className="w-10 h-10 text-violet-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Total Savings</p>
              <p className="text-2xl font-bold text-white mt-1">{savingsPercent.toFixed(1)}%</p>
              <p className="text-xs text-slate-500 mt-1">{formatBytes(totalSavings)} saved</p>
            </div>
            <TrendingUp className="w-10 h-10 text-green-400 opacity-50" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Active Users</p>
              <p className="text-2xl font-bold text-white mt-1">{overview.total_users}</p>
              <p className="text-xs text-slate-500 mt-1">{overview.cached_versions_count} cached</p>
            </div>
            <Users className="w-10 h-10 text-amber-400 opacity-50" />
          </div>
        </div>
      </div>

      {/* Detailed Stats */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Database className="w-5 h-5 text-sky-400" />
          Storage Details
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-slate-400">Compression Ratio</p>
            <p className="text-white font-semibold mt-1">{compressionRatio.toFixed(2)}x</p>
          </div>
          <div>
            <p className="text-slate-400">Compression Savings</p>
            <p className="text-white font-semibold mt-1">{formatBytes(overview.compression_savings_bytes)}</p>
          </div>
          <div>
            <p className="text-slate-400">Dedup Savings</p>
            <p className="text-white font-semibold mt-1">{formatBytes(overview.deduplication_savings_bytes)}</p>
          </div>
          <div>
            <p className="text-slate-400">Unique Blobs</p>
            <p className="text-white font-semibold mt-1">{overview.unique_blobs} / {overview.total_blobs}</p>
          </div>
          <div>
            <p className="text-slate-400">Priority Versions</p>
            <p className="text-white font-semibold mt-1 flex items-center gap-1">
              <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
              {overview.priority_count}
            </p>
          </div>
          <div>
            <p className="text-slate-400">Last Cleanup</p>
            <p className="text-white font-semibold mt-1">
              {overview.last_cleanup_at ? new Date(overview.last_cleanup_at).toLocaleDateString() : 'Never'}
            </p>
          </div>
          <div>
            <p className="text-slate-400">Last Priority Mode</p>
            <p className="text-white font-semibold mt-1">
              {overview.last_priority_mode_at ? new Date(overview.last_priority_mode_at).toLocaleDateString() : 'Never'}
            </p>
          </div>
          <div>
            <p className="text-slate-400">Updated</p>
            <p className="text-white font-semibold mt-1">
              {overview.updated_at ? new Date(overview.updated_at).toLocaleTimeString() : 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Maintenance Actions */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-sky-400" />
          Maintenance
        </h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => handleCleanup(true)}
            disabled={actionLoading}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Dry Run Cleanup
          </button>
          <button
            onClick={() => handleCleanup(false)}
            disabled={actionLoading}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            Trigger Cleanup
          </button>
          <button
            onClick={loadData}
            disabled={actionLoading}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
            Refresh Stats
          </button>
        </div>
      </div>

      {/* User Limits Table */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Users className="w-5 h-5 text-sky-400" />
          User Quotas
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-800">
                <th className="pb-3 text-slate-400 font-medium">User</th>
                <th className="pb-3 text-slate-400 font-medium">Max Size</th>
                <th className="pb-3 text-slate-400 font-medium">Used</th>
                <th className="pb-3 text-slate-400 font-medium">Usage %</th>
                <th className="pb-3 text-slate-400 font-medium">Versions</th>
                <th className="pb-3 text-slate-400 font-medium">Status</th>
                <th className="pb-3 text-slate-400 font-medium">Actions</th>
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
                          {usagePercent.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-3 text-slate-300">{user.total_versions}</td>
                    <td className="py-3">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                          user.is_enabled
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}
                      >
                        {user.is_enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td className="py-3">
                      <button
                        onClick={() => handleEditUser(user)}
                        className="text-sky-400 hover:text-sky-300 transition-colors"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No users found
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
                Edit Settings: {editingUser.username}
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Max Size (bytes)
                </label>
                <input
                  type="number"
                  value={editForm.max_size_bytes || 0}
                  onChange={(e) =>
                    setEditForm({ ...editForm, max_size_bytes: parseInt(e.target.value) || 0 })
                  }
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white"
                />
                <p className="text-xs text-slate-500 mt-1">
                  {formatBytes(editForm.max_size_bytes || 0)}
                </p>
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
                  <span className="text-sm text-slate-300">Enable VCL for this user</span>
                </label>
              </div>
            </div>
            <div className="p-6 border-t border-slate-800 flex justify-end gap-3">
              <button
                onClick={() => setEditingUser(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveUserSettings}
                disabled={actionLoading}
                className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
