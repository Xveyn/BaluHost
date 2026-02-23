/**
 * SSD File Cache Admin Tab (per-array)
 * Array selector, stats, health, configuration, entries table, and cache actions.
 */

import { useState, useEffect } from 'react';
import {
  Zap,
  HardDrive,
  Activity,
  BarChart3,
  Settings,
  Trash2,
  RefreshCw,
  AlertCircle,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  Heart,
  ArrowRightLeft,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { formatBytes } from '../../lib/formatters';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import MigrationPanel from './MigrationPanel';
import { getRaidStatus } from '../../api/raid';
import {
  getCacheStats,
  getCacheConfig,
  updateCacheConfig,
  getCacheEntries,
  evictEntry,
  triggerEviction,
  clearCache,
  getCacheHealth,
} from '../../api/ssd-file-cache';
import type {
  SSDCacheStats,
  SSDCacheConfigResponse,
  SSDCacheConfigUpdate,
  SSDCacheEntryResponse,
  CacheHealthResponse,
} from '../../api/ssd-file-cache';

interface SsdFileCacheTabProps {
  /** Pre-select a specific array (e.g. from RAID card link) */
  initialArray?: string;
}

type TabView = 'cache' | 'migration';

export default function SsdFileCacheTab({ initialArray }: SsdFileCacheTabProps) {
  const { t } = useTranslation();
  const [tabView, setTabView] = useState<TabView>('cache');
  const [arrays, setArrays] = useState<string[]>([]);
  const [selectedArray, setSelectedArray] = useState<string>(initialArray ?? '');
  const [stats, setStats] = useState<SSDCacheStats | null>(null);
  const [config, setConfig] = useState<SSDCacheConfigResponse | null>(null);
  const [health, setHealth] = useState<CacheHealthResponse | null>(null);
  const [entries, setEntries] = useState<SSDCacheEntryResponse[]>([]);
  const [entriesTotal, setEntriesTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Config form
  const [configForm, setConfigForm] = useState<SSDCacheConfigUpdate>({});
  const [configDirty, setConfigDirty] = useState(false);

  // Pagination
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { confirm, dialog } = useConfirmDialog();

  // Load available arrays on mount
  useEffect(() => {
    loadArrays();
  }, []);

  // Load data when selected array changes
  useEffect(() => {
    if (selectedArray) {
      loadData();
      setPage(0);
    }
  }, [selectedArray]);

  useEffect(() => {
    if (selectedArray) {
      loadEntries();
    }
  }, [page, selectedArray]);

  const loadArrays = async () => {
    try {
      const status = await getRaidStatus();
      const arrayNames = (status.arrays ?? []).map((a) => a.name);
      setArrays(arrayNames);

      // Auto-select
      if (initialArray && arrayNames.includes(initialArray)) {
        setSelectedArray(initialArray);
      } else if (arrayNames.length === 1) {
        setSelectedArray(arrayNames[0]);
      } else if (arrayNames.length > 0 && !selectedArray) {
        setSelectedArray(arrayNames[0]);
      }
    } catch {
      setError('Failed to load RAID arrays');
      setLoading(false);
    }
  };

  const loadData = async () => {
    if (!selectedArray) return;
    try {
      setLoading(true);
      setError(null);
      const [statsData, configData, healthData] = await Promise.all([
        getCacheStats(selectedArray),
        getCacheConfig(selectedArray),
        getCacheHealth(selectedArray),
      ]);
      setStats(statsData);
      setConfig(configData);
      setHealth(healthData);
      resetConfigForm(configData);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to load SSD cache data');
    } finally {
      setLoading(false);
    }
  };

  const loadEntries = async () => {
    if (!selectedArray) return;
    try {
      const data = await getCacheEntries(selectedArray, pageSize, page * pageSize);
      setEntries(data.entries);
      setEntriesTotal(data.total);
    } catch {
      // Stats/config already showed error if needed
    }
  };

  const resetConfigForm = (cfg: SSDCacheConfigResponse) => {
    setConfigForm({
      is_enabled: cfg.is_enabled,
      max_size_bytes: cfg.max_size_bytes,
      eviction_policy: cfg.eviction_policy as 'lfru' | 'lru' | 'lfu',
      min_file_size_bytes: cfg.min_file_size_bytes,
      max_file_size_bytes: cfg.max_file_size_bytes,
      sequential_cutoff_bytes: cfg.sequential_cutoff_bytes,
    });
    setConfigDirty(false);
  };

  const handleConfigChange = (key: keyof SSDCacheConfigUpdate, value: unknown) => {
    setConfigForm((prev) => ({ ...prev, [key]: value }));
    setConfigDirty(true);
  };

  const handleSaveConfig = async () => {
    if (!selectedArray) return;
    try {
      setActionLoading(true);
      const updated = await updateCacheConfig(selectedArray, configForm);
      setConfig(updated);
      resetConfigForm(updated);
      toast.success('Cache configuration saved');
      const newStats = await getCacheStats(selectedArray);
      setStats(newStats);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || 'Failed to save configuration');
    } finally {
      setActionLoading(false);
    }
  };

  const handleEvictEntry = async (entryId: number) => {
    if (!selectedArray) return;
    try {
      setActionLoading(true);
      const result = await evictEntry(selectedArray, entryId);
      toast.success(`Evicted: ${result.source_path} (${formatBytes(result.freed_bytes)} freed)`);
      loadEntries();
      const newStats = await getCacheStats(selectedArray);
      setStats(newStats);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || 'Failed to evict entry');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerEviction = async () => {
    if (!selectedArray) return;
    try {
      setActionLoading(true);
      const result = await triggerEviction(selectedArray);
      toast.success(`Eviction complete: ${result.deleted_count} entries removed, ${formatBytes(result.freed_bytes)} freed`);
      loadData();
      loadEntries();
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || 'Eviction failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleClearCache = async () => {
    if (!selectedArray) return;
    const ok = await confirm(
      `This will delete all cached files for ${selectedArray} from the SSD. This action cannot be undone.`,
      {
        title: 'Clear Entire Cache',
        variant: 'danger',
        confirmLabel: 'Clear Cache',
      }
    );
    if (!ok) return;

    try {
      setActionLoading(true);
      const result = await clearCache(selectedArray);
      toast.success(`Cache cleared: ${result.deleted_count} entries removed, ${formatBytes(result.freed_bytes)} freed`);
      loadData();
      setPage(0);
      loadEntries();
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || 'Failed to clear cache');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !selectedArray) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
      </div>
    );
  }

  if (arrays.length === 0 && !loading) {
    return (
      <div className="p-4 bg-slate-800/40 border border-slate-700/50 rounded-lg text-slate-400 text-sm">
        No RAID arrays found. Create a RAID array first to use the SSD file cache.
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
        <AlertCircle className="w-5 h-5 flex-shrink-0" />
        <span className="text-sm">{error}</span>
        <button onClick={loadData} className="ml-auto text-sm text-sky-400 hover:text-sky-300">
          Retry
        </button>
      </div>
    );
  }

  const totalPages = Math.ceil(entriesTotal / pageSize);

  return (
    <div className="space-y-6">
      {/* View Tabs */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setTabView('cache')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${
            tabView === 'cache'
              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
              : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
          }`}
        >
          <Zap className="w-4 h-4" />
          {t('ssdCache.migration.cacheTab', 'File Cache')}
        </button>
        <button
          onClick={() => setTabView('migration')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${
            tabView === 'migration'
              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
              : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
          }`}
        >
          <ArrowRightLeft className="w-4 h-4" />
          {t('ssdCache.migration.title', 'Data Migration')}
        </button>
      </div>

      {tabView === 'migration' ? (
        <MigrationPanel />
      ) : (
      <>
      {/* Array Selector */}
      {arrays.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">Array:</span>
          <div className="flex gap-1.5">
            {arrays.map((name) => (
              <button
                key={name}
                onClick={() => setSelectedArray(name)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                  name === selectedArray
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                    : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
        </div>
      ) : stats && config ? (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Status */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">Status</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      stats.is_enabled
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : 'bg-red-500/20 text-red-300'
                    }`}>
                      {stats.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{stats.total_entries} entries ({stats.valid_entries} valid)</p>
                </div>
                <Zap className="w-10 h-10 text-cyan-400 opacity-50" />
              </div>
            </div>

            {/* Cache Usage */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-slate-400 text-sm">Cache Usage</p>
                  <p className="text-2xl font-bold text-white mt-1">{formatBytes(stats.current_size_bytes)}</p>
                  <p className="text-xs text-slate-500 mt-1">of {formatBytes(stats.max_size_bytes)}</p>
                  <div className="h-1.5 w-full mt-2 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className={`h-full rounded-full transition-all ${
                        stats.usage_percent >= 90 ? 'bg-red-500' : stats.usage_percent >= 70 ? 'bg-amber-500' : 'bg-cyan-500'
                      }`}
                      style={{ width: `${Math.min(stats.usage_percent, 100)}%` }}
                    />
                  </div>
                </div>
                <HardDrive className="w-10 h-10 text-violet-400 opacity-50 flex-shrink-0 ml-3" />
              </div>
            </div>

            {/* Hit Rate */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">Hit Rate</p>
                  <p className="text-2xl font-bold text-white mt-1">{stats.hit_rate_percent.toFixed(1)}%</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {stats.total_hits.toLocaleString()} hits / {stats.total_misses.toLocaleString()} misses
                  </p>
                </div>
                <BarChart3 className="w-10 h-10 text-green-400 opacity-50" />
              </div>
            </div>

            {/* Bytes Served */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">Bytes Served</p>
                  <p className="text-2xl font-bold text-white mt-1">{formatBytes(stats.total_bytes_served)}</p>
                  <p className="text-xs text-slate-500 mt-1">from SSD cache</p>
                </div>
                <Activity className="w-10 h-10 text-amber-400 opacity-50" />
              </div>
            </div>
          </div>

          {/* Health Card */}
          {health && (
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Heart className="w-5 h-5 text-sky-400" />
                SSD Health
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-slate-400">SSD Mount</p>
                  <p className={`font-semibold mt-1 flex items-center gap-1 ${health.is_mounted ? 'text-emerald-400' : 'text-red-400'}`}>
                    {health.is_mounted ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                    {health.is_mounted ? 'Mounted' : 'Not Mounted'}
                  </p>
                </div>
                <div>
                  <p className="text-slate-400">Disk Free</p>
                  <p className="text-white font-semibold mt-1">{formatBytes(health.ssd_available_bytes)}</p>
                </div>
                <div>
                  <p className="text-slate-400">Disk Used</p>
                  <p className="text-white font-semibold mt-1">{health.ssd_used_percent.toFixed(1)}% of {formatBytes(health.ssd_total_bytes)}</p>
                </div>
                <div>
                  <p className="text-slate-400">Cache Directory</p>
                  <p className={`font-semibold mt-1 flex items-center gap-1 ${health.cache_dir_exists ? 'text-emerald-400' : 'text-red-400'}`}>
                    {health.cache_dir_exists ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                    {health.cache_dir_exists ? 'Exists' : 'Missing'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Config Card */}
          <div className="card border-slate-800/60 bg-slate-900/55">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Settings className="w-5 h-5 text-sky-400" />
              Configuration
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Enable/Disable */}
              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={configForm.is_enabled ?? false}
                    onChange={(e) => handleConfigChange('is_enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-slate-700 bg-slate-800"
                  />
                  <span className="text-sm text-slate-300">Cache Enabled</span>
                </label>
              </div>

              {/* Max Size */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Max Size (bytes)</label>
                <input
                  type="number"
                  value={configForm.max_size_bytes ?? 0}
                  onChange={(e) => handleConfigChange('max_size_bytes', parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-slate-500 mt-1">{formatBytes(configForm.max_size_bytes ?? 0)}</p>
              </div>

              {/* Eviction Policy */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Eviction Policy</label>
                <select
                  value={configForm.eviction_policy ?? 'lfru'}
                  onChange={(e) => handleConfigChange('eviction_policy', e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
                >
                  <option value="lfru">LFRU (Least Frequently + Recently Used)</option>
                  <option value="lru">LRU (Least Recently Used)</option>
                  <option value="lfu">LFU (Least Frequently Used)</option>
                </select>
              </div>

              {/* Min File Size */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Min File Size</label>
                <input
                  type="number"
                  value={configForm.min_file_size_bytes ?? 0}
                  onChange={(e) => handleConfigChange('min_file_size_bytes', parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-slate-500 mt-1">{formatBytes(configForm.min_file_size_bytes ?? 0)}</p>
              </div>

              {/* Max File Size */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Max File Size</label>
                <input
                  type="number"
                  value={configForm.max_file_size_bytes ?? 0}
                  onChange={(e) => handleConfigChange('max_file_size_bytes', parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-slate-500 mt-1">{formatBytes(configForm.max_file_size_bytes ?? 0)}</p>
              </div>

              {/* Sequential Cutoff */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Sequential Cutoff</label>
                <input
                  type="number"
                  value={configForm.sequential_cutoff_bytes ?? 0}
                  onChange={(e) => handleConfigChange('sequential_cutoff_bytes', parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-slate-500 mt-1">{formatBytes(configForm.sequential_cutoff_bytes ?? 0)}</p>
              </div>
            </div>

            {/* Save / Reset */}
            <div className="flex gap-3 mt-4 pt-4 border-t border-slate-800/60">
              <button
                onClick={handleSaveConfig}
                disabled={actionLoading || !configDirty}
                className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
              >
                <Check className="w-4 h-4" />
                Save Configuration
              </button>
              {configDirty && config && (
                <button
                  onClick={() => resetConfigForm(config)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors text-sm"
                >
                  Reset
                </button>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="card border-slate-800/60 bg-slate-900/55">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <RefreshCw className="w-5 h-5 text-sky-400" />
              Actions
            </h3>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={handleTriggerEviction}
                disabled={actionLoading}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
              >
                <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
                Trigger Eviction
              </button>
              <button
                onClick={handleClearCache}
                disabled={actionLoading}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
              >
                <Trash2 className="w-4 h-4" />
                Clear Cache
              </button>
              <button
                onClick={() => { loadData(); loadEntries(); }}
                disabled={actionLoading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
              >
                <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Entries Table */}
          <div className="card border-slate-800/60 bg-slate-900/55">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <HardDrive className="w-5 h-5 text-sky-400" />
                Cached Entries
                <span className="text-sm font-normal text-slate-400">({entriesTotal})</span>
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b border-slate-800">
                    <th className="pb-3 text-slate-400 font-medium">Source Path</th>
                    <th className="pb-3 text-slate-400 font-medium">Size</th>
                    <th className="pb-3 text-slate-400 font-medium">Accesses</th>
                    <th className="pb-3 text-slate-400 font-medium">Last Accessed</th>
                    <th className="pb-3 text-slate-400 font-medium">Status</th>
                    <th className="pb-3 text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.length > 0 ? entries.map((entry) => (
                    <tr key={entry.id} className="border-b border-slate-800/50">
                      <td className="py-3 text-slate-300 max-w-xs truncate" title={entry.source_path}>
                        {entry.source_path}
                      </td>
                      <td className="py-3 text-slate-300">{formatBytes(entry.file_size_bytes)}</td>
                      <td className="py-3 text-slate-300">{entry.access_count}</td>
                      <td className="py-3 text-slate-300">
                        {new Date(entry.last_accessed).toLocaleString()}
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          entry.is_valid
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}>
                          {entry.is_valid ? 'Valid' : 'Invalid'}
                        </span>
                      </td>
                      <td className="py-3">
                        <button
                          onClick={() => handleEvictEntry(entry.id)}
                          disabled={actionLoading}
                          className="text-red-400 hover:text-red-300 transition-colors disabled:opacity-50 text-xs"
                        >
                          Evict
                        </button>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-500">
                        No cached entries
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-800/60">
                <p className="text-sm text-slate-400">
                  Page {page + 1} of {totalPages}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      ) : null}

      {dialog}
      </>
      )}
    </div>
  );
}
