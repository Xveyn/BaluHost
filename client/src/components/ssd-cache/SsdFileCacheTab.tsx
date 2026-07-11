/**
 * SSD File Cache Admin Tab (per-array)
 * Array selector, stats, health, configuration, entries table, and cache actions.
 */

import { AlertCircle } from 'lucide-react';
import MigrationPanel from './MigrationPanel';
import { useSsdFileCache } from '../../hooks/useSsdFileCache';
import {
  CacheViewTabs,
  CacheArraySelector,
  CacheStatsGrid,
  CacheHealthCard,
  CacheConfigCard,
  CacheActionsCard,
  CacheEntriesTable,
} from './file-cache';

interface SsdFileCacheTabProps {
  /** Pre-select a specific array (e.g. from RAID card link) */
  initialArray?: string;
}

export default function SsdFileCacheTab({ initialArray }: SsdFileCacheTabProps) {
  const {
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
  } = useSsdFileCache(initialArray);

  const totalPages = Math.ceil(entriesTotal / pageSize);

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

  return (
    <div className="space-y-6">
      <CacheViewTabs tabView={tabView} onSelect={setTabView} />

      {tabView === 'migration' ? (
        <MigrationPanel />
      ) : (
      <>
      {arrays.length > 1 && (
        <CacheArraySelector arrays={arrays} selectedArray={selectedArray} onSelect={setSelectedArray} />
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
        </div>
      ) : stats && config ? (
        <>
          <CacheStatsGrid stats={stats} />

          {health && <CacheHealthCard health={health} />}

          <CacheConfigCard
            configForm={configForm}
            config={config}
            configDirty={configDirty}
            actionLoading={actionLoading}
            onConfigChange={handleConfigChange}
            onSave={handleSaveConfig}
            onReset={resetConfigForm}
          />

          <CacheActionsCard
            actionLoading={actionLoading}
            onTriggerEviction={handleTriggerEviction}
            onClearCache={handleClearCache}
            onRefresh={() => { loadData(); loadEntries(); }}
          />

          <CacheEntriesTable
            entries={entries}
            entriesTotal={entriesTotal}
            page={page}
            totalPages={totalPages}
            actionLoading={actionLoading}
            onEvict={handleEvictEntry}
            onPrevPage={() => setPage((p) => Math.max(0, p - 1))}
            onNextPage={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          />
        </>
      ) : null}

      {dialog}
      </>
      )}
    </div>
  );
}
