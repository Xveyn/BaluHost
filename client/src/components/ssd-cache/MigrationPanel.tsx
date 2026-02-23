/**
 * VCL Data Migration Panel — migrate VCL blobs from HDD to SSD.
 * Steps: migrate → verify → cleanup.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  ArrowRightLeft,
  Play,
  CheckCircle2,
  XCircle,
  Trash2,
  Clock,
  Loader2,
  AlertCircle,
  Ban,
  FileCheck,
  Info,
  FolderSearch,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { formatBytes } from '../../lib/formatters';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import { getStorageInfo } from '../../api/vcl';
import type { VCLStorageInfo } from '../../types/vcl';
import {
  startVCLMigration,
  startVCLVerify,
  startVCLCleanup,
  getMigrationJobs,
  getMigrationJob,
  cancelMigrationJob,
} from '../../api/migration';
import type { MigrationJobResponse } from '../../api/migration';
import SystemDirPicker from './SystemDirPicker';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-300',
  running: 'bg-sky-500/20 text-sky-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
  cancelled: 'bg-slate-500/20 text-slate-400',
};

const STATUS_ICONS: Record<string, typeof Clock> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
};

export default function MigrationPanel() {
  const { t } = useTranslation();
  const { confirm, dialog } = useConfirmDialog();

  // VCL Storage info
  const [storageInfo, setStorageInfo] = useState<VCLStorageInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // Form
  const [sourcePath, setSourcePath] = useState('');
  const [destPath, setDestPath] = useState('');
  const [dryRun, setDryRun] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Browse picker
  const [browseTarget, setBrowseTarget] = useState<'source' | 'dest' | null>(null);

  // Active job tracking
  const [activeJob, setActiveJob] = useState<MigrationJobResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Job history
  const [jobs, setJobs] = useState<MigrationJobResponse[]>([]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [info, jobList] = await Promise.all([
        getStorageInfo(),
        getMigrationJobs(),
      ]);
      setStorageInfo(info);
      setJobs(jobList);

      // Pre-fill paths from storage info
      if (info.storage_path && !sourcePath) {
        setSourcePath(info.storage_path);
      }
      if (!destPath) {
        setDestPath('/mnt/cache-vcl/vcl');
      }

      // Check for active job
      const running = jobList.find((j) => j.status === 'running' || j.status === 'pending');
      if (running) {
        setActiveJob(running);
        startPolling(running.id);
      }
    } catch {
      // Non-critical — panel still renders
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    return () => stopPolling();
  }, [loadData]);

  const startPolling = (jobId: number) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const job = await getMigrationJob(jobId);
        setActiveJob(job);
        if (job.status !== 'running' && job.status !== 'pending') {
          stopPolling();
          loadData();
        }
      } catch {
        stopPolling();
      }
    }, 3000);
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const handleStartMigration = async () => {
    if (!sourcePath || !destPath) return;
    try {
      setActionLoading(true);
      const job = await startVCLMigration({
        source_path: sourcePath,
        dest_path: destPath,
        dry_run: dryRun,
      });
      setActiveJob(job);
      startPolling(job.id);
      toast.success(dryRun
        ? t('ssdCache.migration.dryRunStarted', 'Dry-run started')
        : t('ssdCache.migration.migrationStarted', 'Migration started')
      );
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || t('ssdCache.migration.startFailed', 'Failed to start migration'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!destPath) return;
    try {
      setActionLoading(true);
      const job = await startVCLVerify({ dest_path: destPath });
      setActiveJob(job);
      startPolling(job.id);
      toast.success(t('ssdCache.migration.verifyStarted', 'Verification started'));
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || t('ssdCache.migration.verifyFailed', 'Failed to start verification'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCleanup = async () => {
    const ok = await confirm(
      t('ssdCache.migration.confirmCleanup', 'This will permanently delete the source VCL blobs. Make sure verification passed before proceeding.'),
      {
        title: t('ssdCache.migration.cleanup', 'Cleanup Source Files'),
        variant: 'danger',
        confirmLabel: t('ssdCache.migration.cleanup', 'Cleanup'),
      }
    );
    if (!ok) return;

    try {
      setActionLoading(true);
      const job = await startVCLCleanup({
        source_path: sourcePath,
        dry_run: dryRun,
      });
      setActiveJob(job);
      startPolling(job.id);
      toast.success(dryRun
        ? t('ssdCache.migration.dryRunStarted', 'Dry-run started')
        : t('ssdCache.migration.cleanupStarted', 'Cleanup started')
      );
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || t('ssdCache.migration.cleanupFailed', 'Failed to start cleanup'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!activeJob) return;
    try {
      await cancelMigrationJob(activeJob.id);
      toast.success(t('ssdCache.migration.cancelled', 'Job cancelled'));
    } catch {
      toast.error(t('ssdCache.migration.cancelFailed', 'Failed to cancel job'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-sky-500" />
      </div>
    );
  }

  const isActive = activeJob && (activeJob.status === 'running' || activeJob.status === 'pending');
  const lastCompleted = jobs.find((j) => j.job_type === 'vcl_to_ssd' && j.status === 'completed');
  const lastVerify = jobs.find((j) => j.job_type === 'vcl_verify' && j.status === 'completed');

  return (
    <div className="space-y-6">
      {/* VCL Storage Info */}
      {storageInfo && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Info className="w-5 h-5 text-sky-400" />
            {t('ssdCache.migration.vclInfo', 'VCL Storage Info')}
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.storagePath', 'Storage Path')}</p>
              <p className="text-white font-mono text-xs mt-1 break-all">{storageInfo.storage_path}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.blobCount', 'Blob Count')}</p>
              <p className="text-white font-semibold mt-1">{storageInfo.blob_count.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.totalSize', 'Compressed Size')}</p>
              <p className="text-white font-semibold mt-1">{formatBytes(storageInfo.total_compressed_bytes)}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.diskFree', 'Disk Available')}</p>
              <p className="text-white font-semibold mt-1">{formatBytes(storageInfo.disk_available_bytes)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Migration Form */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <ArrowRightLeft className="w-5 h-5 text-sky-400" />
          {t('ssdCache.migration.vclMigration', 'VCL Blob Migration')}
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">
              {t('ssdCache.migration.sourcePath', 'Source Path (HDD)')}
            </label>
            <div className="flex items-center gap-2">
              <div className="flex-1 min-w-0 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm font-mono truncate">
                <span className={sourcePath ? 'text-white' : 'text-slate-500'}>
                  {sourcePath || '/mnt/md1/.system/versions'}
                </span>
              </div>
              <button
                onClick={() => setBrowseTarget('source')}
                disabled={!!isActive}
                className="shrink-0 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 text-sm"
              >
                <FolderSearch className="w-4 h-4" />
                {t('ssdCache.migration.browse', 'Browse')}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">
              {t('ssdCache.migration.destPath', 'Destination Path (SSD)')}
            </label>
            <div className="flex items-center gap-2">
              <div className="flex-1 min-w-0 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm font-mono truncate">
                <span className={destPath ? 'text-white' : 'text-slate-500'}>
                  {destPath || '/mnt/cache-vcl/vcl'}
                </span>
              </div>
              <button
                onClick={() => setBrowseTarget('dest')}
                disabled={!!isActive}
                className="shrink-0 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 text-sm"
              >
                <FolderSearch className="w-4 h-4" />
                {t('ssdCache.migration.browse', 'Browse')}
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 mb-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              disabled={!!isActive}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800"
            />
            <span className="text-sm text-slate-300">
              {t('ssdCache.migration.dryRun', 'Dry Run')}
            </span>
          </label>
          <span className="text-xs text-slate-500">
            {t('ssdCache.migration.dryRunHint', 'Simulate without copying files')}
          </span>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleStartMigration}
            disabled={actionLoading || !!isActive || !sourcePath || !destPath}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
          >
            <Play className="w-4 h-4" />
            {t('ssdCache.migration.startMigration', 'Start Migration')}
          </button>

          <button
            onClick={handleVerify}
            disabled={actionLoading || !!isActive || !destPath || !lastCompleted}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
            title={!lastCompleted ? t('ssdCache.migration.verifyRequiresMigration', 'Complete a migration first') : ''}
          >
            <FileCheck className="w-4 h-4" />
            {t('ssdCache.migration.verify', 'Verify')}
          </button>

          <button
            onClick={handleCleanup}
            disabled={actionLoading || !!isActive || !sourcePath || !lastVerify}
            className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
            title={!lastVerify ? t('ssdCache.migration.cleanupRequiresVerify', 'Complete verification first') : ''}
          >
            <Trash2 className="w-4 h-4" />
            {t('ssdCache.migration.cleanup', 'Cleanup')}
          </button>
        </div>

        {/* VCL Storage Path Hint */}
        {lastCompleted && !lastCompleted.dry_run && (
          <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-amber-300 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              {t('ssdCache.migration.vclStorageHint', 'After migration, update VCL_STORAGE_PATH in .env.production to point to the new SSD path and restart the backend.')}
            </div>
          </div>
        )}
      </div>

      {/* Active Job Progress */}
      {activeJob && (activeJob.status === 'running' || activeJob.status === 'pending') && (
        <div className="card border-sky-500/30 bg-slate-900/55">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Loader2 className="w-5 h-5 text-sky-400 animate-spin" />
              {t('ssdCache.migration.activeJob', 'Active Job')}
              <span className="text-sm font-normal text-slate-400">#{activeJob.id}</span>
            </h3>
            <button
              onClick={handleCancel}
              className="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors text-sm flex items-center gap-1.5"
            >
              <Ban className="w-3.5 h-3.5" />
              {t('ssdCache.migration.cancel', 'Cancel')}
            </button>
          </div>

          {/* Progress Bar */}
          <div className="mb-3">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-slate-400">
                {activeJob.processed_files.toLocaleString()} / {activeJob.total_files.toLocaleString()} {t('ssdCache.migration.files', 'files')}
              </span>
              <span className="text-white font-semibold">{activeJob.progress_percent}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-500"
                style={{ width: `${Math.min(activeJob.progress_percent, 100)}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.processed', 'Processed')}</p>
              <p className="text-white">{formatBytes(activeJob.processed_bytes)}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.skipped', 'Skipped')}</p>
              <p className="text-white">{activeJob.skipped_files.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('ssdCache.migration.failed', 'Failed')}</p>
              <p className={activeJob.failed_files > 0 ? 'text-red-400' : 'text-white'}>
                {activeJob.failed_files.toLocaleString()}
              </p>
            </div>
            {activeJob.current_file && (
              <div className="col-span-2 md:col-span-1">
                <p className="text-slate-400">{t('ssdCache.migration.currentFile', 'Current')}</p>
                <p className="text-white font-mono text-xs truncate">{activeJob.current_file}</p>
              </div>
            )}
          </div>

          {activeJob.dry_run && (
            <div className="mt-3 px-2 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400 inline-block">
              {t('ssdCache.migration.dryRunLabel', 'DRY RUN — no files are being modified')}
            </div>
          )}
        </div>
      )}

      {/* Job History */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-sky-400" />
          {t('ssdCache.migration.jobHistory', 'Job History')}
        </h3>

        {jobs.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-4">
            {t('ssdCache.migration.noJobs', 'No migration jobs yet')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-slate-800">
                  <th className="pb-3 text-slate-400 font-medium">ID</th>
                  <th className="pb-3 text-slate-400 font-medium">{t('ssdCache.migration.type', 'Type')}</th>
                  <th className="pb-3 text-slate-400 font-medium">{t('ssdCache.migration.statusLabel', 'Status')}</th>
                  <th className="pb-3 text-slate-400 font-medium">{t('ssdCache.migration.files', 'Files')}</th>
                  <th className="pb-3 text-slate-400 font-medium">{t('ssdCache.migration.duration', 'Duration')}</th>
                  <th className="pb-3 text-slate-400 font-medium">{t('ssdCache.migration.date', 'Date')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const StatusIcon = STATUS_ICONS[job.status] ?? Clock;
                  return (
                    <tr key={job.id} className="border-b border-slate-800/50">
                      <td className="py-3 text-slate-300">#{job.id}</td>
                      <td className="py-3 text-slate-300">
                        <span className="font-mono text-xs">{job.job_type}</span>
                        {job.dry_run && (
                          <span className="ml-1 text-xs text-yellow-400">(dry)</span>
                        )}
                      </td>
                      <td className="py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[job.status] ?? ''}`}>
                          <StatusIcon className={`w-3 h-3 ${job.status === 'running' ? 'animate-spin' : ''}`} />
                          {job.status}
                        </span>
                      </td>
                      <td className="py-3 text-slate-300">
                        {job.processed_files}/{job.total_files}
                        {job.failed_files > 0 && (
                          <span className="text-red-400 ml-1">({job.failed_files} failed)</span>
                        )}
                      </td>
                      <td className="py-3 text-slate-300">
                        {job.duration_seconds != null ? `${job.duration_seconds.toFixed(1)}s` : '—'}
                      </td>
                      <td className="py-3 text-slate-300 text-xs">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Directory Browser */}
      {browseTarget && (
        <SystemDirPicker
          title={
            browseTarget === 'source'
              ? t('ssdCache.migration.selectSource', 'Select Source Directory')
              : t('ssdCache.migration.selectDest', 'Select Destination Directory')
          }
          initialPath={browseTarget === 'source' ? (sourcePath || '/mnt') : (destPath || '/mnt')}
          onSelect={(path) => {
            if (browseTarget === 'source') setSourcePath(path);
            else setDestPath(path);
            setBrowseTarget(null);
          }}
          onClose={() => setBrowseTarget(null)}
        />
      )}

      {dialog}
    </div>
  );
}
