/**
 * SSD File Cache Admin data/state hook (per-array)
 * Owns all state, effects, and handlers for SsdFileCacheTab.
 */

import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { getApiErrorMessage, handleApiError } from '../lib/errorHandling';
import { formatBytes } from '../lib/formatters';
import { useConfirmDialog } from './useConfirmDialog';
import { getRaidStatus } from '../api/raid';
import {
  getCacheStats,
  getCacheConfig,
  updateCacheConfig,
  getCacheEntries,
  evictEntry,
  triggerEviction,
  clearCache,
  getCacheHealth,
} from '../api/ssd-file-cache';
import type {
  SSDCacheStats,
  SSDCacheConfigResponse,
  SSDCacheConfigUpdate,
  SSDCacheEntryResponse,
  CacheHealthResponse,
} from '../api/ssd-file-cache';
import type { Dispatch, SetStateAction, ReactNode } from 'react';

export type TabView = 'cache' | 'migration';

export interface UseSsdFileCacheResult {
  tabView: TabView;
  setTabView: (v: TabView) => void;
  arrays: string[];
  selectedArray: string;
  setSelectedArray: (name: string) => void;
  stats: SSDCacheStats | null;
  config: SSDCacheConfigResponse | null;
  health: CacheHealthResponse | null;
  entries: SSDCacheEntryResponse[];
  entriesTotal: number;
  loading: boolean;
  error: string | null;
  actionLoading: boolean;
  configForm: SSDCacheConfigUpdate;
  configDirty: boolean;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  pageSize: number;
  handleConfigChange: (key: keyof SSDCacheConfigUpdate, value: unknown) => void;
  handleSaveConfig: () => Promise<void>;
  resetConfigForm: (cfg: SSDCacheConfigResponse) => void;
  handleEvictEntry: (entryId: number) => Promise<void>;
  handleTriggerEviction: () => Promise<void>;
  handleClearCache: () => Promise<void>;
  loadData: () => Promise<void>;
  loadEntries: () => Promise<void>;
  dialog: ReactNode;
}

export function useSsdFileCache(initialArray?: string): UseSsdFileCacheResult {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load data when selected array changes
  useEffect(() => {
    if (selectedArray) {
      loadData();
      setPage(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedArray]);

  useEffect(() => {
    if (selectedArray) {
      loadEntries();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setError(getApiErrorMessage(err, 'Failed to load SSD cache data'));
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
      handleApiError(err, 'Failed to save configuration');
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
      handleApiError(err, 'Failed to evict entry');
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
      handleApiError(err, 'Eviction failed');
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
      handleApiError(err, 'Failed to clear cache');
    } finally {
      setActionLoading(false);
    }
  };

  return {
    tabView,
    setTabView,
    arrays,
    selectedArray,
    setSelectedArray,
    stats,
    config,
    health,
    entries,
    entriesTotal,
    loading,
    error,
    actionLoading,
    configForm,
    configDirty,
    page,
    setPage,
    pageSize,
    handleConfigChange,
    handleSaveConfig,
    resetConfigForm,
    handleEvictEntry,
    handleTriggerEviction,
    handleClearCache,
    loadData,
    loadEntries,
    dialog,
  };
}
