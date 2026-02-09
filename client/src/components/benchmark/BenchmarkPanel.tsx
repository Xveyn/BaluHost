/**
 * BenchmarkPanel component
 *
 * Main panel for disk benchmarking that includes:
 * - Disk and profile selection
 * - Start benchmark button
 * - Progress display during benchmark
 * - Results display (CrystalDiskMark style)
 * - Benchmark history (collapsible)
 */
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Play,
  History,
  ChevronDown,
  ChevronUp,
  HardDrive,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
  Gauge,
} from 'lucide-react';
import toast from 'react-hot-toast';

import {
  useBenchmarkDisks,
  useBenchmarkProfiles,
  useBenchmarkProgress,
  useBenchmarkHistory,
  useStartBenchmark,
  useCancelBenchmark,
  useMarkBenchmarkFailed,
  useBenchmark,
  getBenchmarkStatusBgColor,
  formatBenchmarkStatus,
} from '../../hooks/useBenchmark';
import { formatDuration } from '../../api/benchmark';
import type { BenchmarkProfile, BenchmarkStatus, BenchmarkResponse } from '../../api/benchmark';

import { formatNumber } from '../../lib/formatters';
import BenchmarkProgress from './BenchmarkProgress';
import BenchmarkResults, { BenchmarkResultsCompact } from './BenchmarkResults';

export default function BenchmarkPanel() {
  const { t } = useTranslation('system');
  // State
  const [selectedDisk, setSelectedDisk] = useState<string>('');
  const [selectedProfile, setSelectedProfile] = useState<BenchmarkProfile>('quick');
  const [activeBenchmarkId, setActiveBenchmarkId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  // Hooks
  const { disks, loading: disksLoading, error: disksError } = useBenchmarkDisks();
  const { profiles, loading: profilesLoading } = useBenchmarkProfiles();
  const { start, loading: startLoading, error: startError } = useStartBenchmark();
  const { cancel, loading: cancelLoading } = useCancelBenchmark();
  const { benchmark: activeBenchmark, refetch: refetchBenchmark } = useBenchmark(activeBenchmarkId);
  const { progress, startPolling, stopPolling } = useBenchmarkProgress(activeBenchmarkId);
  const { benchmarks: historyBenchmarks, loading: historyLoading, refetch: refetchHistory } = useBenchmarkHistory(5);

  // Set default disk when disks load
  useEffect(() => {
    if (disks.length > 0 && !selectedDisk) {
      // Select first benchmarkable disk
      const firstBenchmarkable = disks.find(d => d.can_benchmark);
      if (firstBenchmarkable) {
        setSelectedDisk(firstBenchmarkable.name);
      } else {
        setSelectedDisk(disks[0].name);
      }
    }
  }, [disks, selectedDisk]);

  // Handle benchmark completion
  useEffect(() => {
    if (progress && isCompleteStatus(progress.status)) {
      stopPolling();
      refetchBenchmark();
      refetchHistory();

      if (progress.status === 'completed') {
        toast.success('Benchmark completed successfully!');
      } else if (progress.status === 'cancelled') {
        toast('Benchmark cancelled', { icon: '⚠️' });
      } else if (progress.status === 'failed') {
        toast.error('Benchmark failed');
      }
    }
  }, [progress, stopPolling, refetchBenchmark, refetchHistory]);

  // Start benchmark handler
  const handleStartBenchmark = useCallback(async () => {
    if (!selectedDisk) {
      toast.error('Please select a disk');
      return;
    }

    const disk = disks.find(d => d.name === selectedDisk);
    if (disk && !disk.can_benchmark) {
      toast.error(`Cannot benchmark ${selectedDisk}: ${disk.warning || 'Disk not available'}`);
      return;
    }

    try {
      const benchmark = await start({
        disk_name: selectedDisk,
        profile: selectedProfile,
      });

      setActiveBenchmarkId(benchmark.id);
      startPolling();
      toast.success('Benchmark started!');
    } catch (err) {
      // Error is already handled in the hook
    }
  }, [selectedDisk, selectedProfile, disks, start, startPolling]);

  // Cancel benchmark handler
  const handleCancelBenchmark = useCallback(async () => {
    if (activeBenchmarkId === null) return;

    try {
      await cancel(activeBenchmarkId);
      toast.success('Cancellation requested');
    } catch (err) {
      toast.error('Failed to cancel benchmark');
    }
  }, [activeBenchmarkId, cancel]);

  // Get selected disk info
  const selectedDiskInfo = disks.find(d => d.name === selectedDisk);
  const selectedProfileInfo = profiles.find(p => p.name === selectedProfile);

  // Check if benchmark is running
  const isRunning = progress?.status === 'running' || progress?.status === 'pending';

  return (
    <div className="space-y-4">
      {/* Section Header */}
      <div className="flex items-center gap-2">
        <Gauge className="w-5 h-5 text-sky-500" />
        <h3 className="text-lg font-semibold text-white">{t('benchmark.title')}</h3>
        <span className="text-xs text-slate-500 ml-2">({t('benchmark.crystalDiskMarkStyle')})</span>
      </div>

      {/* Error display */}
      {(disksError || startError) && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {disksError || startError}
        </div>
      )}

      {/* Configuration section (only show when not running) */}
      {!isRunning && (
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Disk selection */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1.5">
                {t('benchmark.selectDisk')}
              </label>
              <div className="relative">
                <HardDrive className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <select
                  value={selectedDisk}
                  onChange={e => setSelectedDisk(e.target.value)}
                  disabled={disksLoading || isRunning}
                  className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
                >
                  {disksLoading && <option>{t('benchmark.loadingDisks')}</option>}
                  {disks.map(disk => (
                    <option key={disk.name} value={disk.name} disabled={!disk.can_benchmark}>
                      {disk.name} - {disk.size_display} {disk.model ? `(${disk.model})` : ''}{' '}
                      {!disk.can_benchmark && '⚠️'}
                    </option>
                  ))}
                </select>
              </div>
              {selectedDiskInfo && !selectedDiskInfo.can_benchmark && (
                <p className="mt-1.5 text-xs text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" />
                  {selectedDiskInfo.warning}
                </p>
              )}
            </div>

            {/* Profile selection */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1.5">
                {t('benchmark.profile')}
              </label>
              <select
                value={selectedProfile}
                onChange={e => setSelectedProfile(e.target.value as BenchmarkProfile)}
                disabled={profilesLoading || isRunning}
                className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
              >
                {profiles.map(profile => (
                  <option key={profile.name} value={profile.name}>
                    {profile.display_name} (~{formatDuration(profile.estimated_duration_seconds)})
                  </option>
                ))}
              </select>
              {selectedProfileInfo && (
                <p className="mt-1.5 text-xs text-slate-500">
                  {selectedProfileInfo.description}
                </p>
              )}
            </div>
          </div>

          {/* Start button */}
          <div className="mt-4 flex justify-end">
            <button
              onClick={handleStartBenchmark}
              disabled={startLoading || isRunning || !selectedDiskInfo?.can_benchmark}
              className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 disabled:bg-slate-700 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
            >
              {startLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {t('benchmark.start')}
            </button>
          </div>
        </div>
      )}

      {/* Progress section (when running) */}
      {isRunning && progress && (
        <BenchmarkProgress
          progress={progress}
          onCancel={handleCancelBenchmark}
          cancelLoading={cancelLoading}
        />
      )}

      {/* Results section (after completion) */}
      {activeBenchmark && activeBenchmark.status === 'completed' && (
        <BenchmarkResults
          results={activeBenchmark.summary}
          diskName={activeBenchmark.disk_name}
          diskModel={activeBenchmark.disk_model}
        />
      )}

      {/* Failed benchmark message */}
      {activeBenchmark && activeBenchmark.status === 'failed' && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg px-4 py-3">
          <div className="flex items-center gap-2 text-red-300">
            <XCircle className="w-5 h-5" />
            <span className="font-medium">{t('benchmark.failed')}</span>
          </div>
          {activeBenchmark.error_message && (
            <p className="mt-2 text-sm text-red-400">{activeBenchmark.error_message}</p>
          )}
        </div>
      )}

      {/* History section */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-700/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-slate-400" />
            <span className="font-medium text-white">{t('benchmark.history')}</span>
            <span className="text-sm text-slate-500">({historyBenchmarks.length} {t('benchmark.recent')})</span>
          </div>
          {showHistory ? (
            <ChevronUp className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          )}
        </button>

        {showHistory && (
          <div className="border-t border-slate-700">
            {historyLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
              </div>
            ) : historyBenchmarks.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                {t('benchmark.noHistory')}
              </div>
            ) : (
              <div className="divide-y divide-slate-700">
                {historyBenchmarks.map(benchmark => (
                  <HistoryItem key={benchmark.id} benchmark={benchmark} onRefetch={refetchHistory} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// History item component
function HistoryItem({ benchmark, onRefetch }: { benchmark: BenchmarkResponse; onRefetch: () => Promise<void> }) {
  const [expanded, setExpanded] = useState(false);
  const { markFailed, loading: markFailedLoading } = useMarkBenchmarkFailed();

  const statusIcon = getStatusIcon(benchmark.status);
  const statusColorClass = getBenchmarkStatusBgColor(benchmark.status);
  const isStuck = benchmark.status === 'running' || benchmark.status === 'pending';

  const handleMarkFailed = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await markFailed(benchmark.id);
      toast.success('Benchmark marked as failed');
      await onRefetch();
    } catch {
      toast.error('Failed to mark benchmark as failed');
    }
  };

  return (
    <div className="px-4 py-3">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {statusIcon}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-white">{benchmark.disk_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${statusColorClass}`}>
                {formatBenchmarkStatus(benchmark.status)}
              </span>
            </div>
            <div className="text-xs text-slate-500 mt-0.5">
              {new Date(benchmark.created_at).toLocaleString()} • {benchmark.profile} profile
              {benchmark.duration_seconds && ` • ${formatDuration(benchmark.duration_seconds)}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isStuck && (
            <button
              onClick={handleMarkFailed}
              disabled={markFailedLoading}
              className="text-xs px-2 py-1 bg-red-900/50 hover:bg-red-800/60 border border-red-700 text-red-300 rounded transition-colors disabled:opacity-50"
            >
              {markFailedLoading ? 'Marking...' : 'Mark Failed'}
            </button>
          )}
          {benchmark.status === 'completed' && (
            <div className="text-right text-sm">
              <div className="text-sky-400">{benchmark.summary.seq_read_mbps != null ? formatNumber(benchmark.summary.seq_read_mbps, 0) : '-'} MB/s</div>
              <div className="text-xs text-slate-500">seq read</div>
            </div>
          )}
        </div>
      </div>

      {/* Expanded results */}
      {expanded && benchmark.status === 'completed' && (
        <div className="mt-3 pt-3 border-t border-slate-700">
          <BenchmarkResultsCompact results={benchmark.summary} />
        </div>
      )}
    </div>
  );
}

// Helper functions
function isCompleteStatus(status: BenchmarkStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

function getStatusIcon(status: BenchmarkStatus) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-5 h-5 text-green-500" />;
    case 'running':
      return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
    case 'pending':
      return <Clock className="w-5 h-5 text-yellow-500" />;
    case 'failed':
      return <XCircle className="w-5 h-5 text-red-500" />;
    case 'cancelled':
      return <XCircle className="w-5 h-5 text-gray-500" />;
    default:
      return <HardDrive className="w-5 h-5 text-slate-500" />;
  }
}
