/**
 * UpdateProgress component
 *
 * Shows real-time progress during an update with:
 * - Progress bar with percentage
 * - Current step description
 * - Version transition (from -> to)
 * - Status indicator
 * - Rollback option (when failed)
 */
import { Loader2, Clock, AlertTriangle, CheckCircle, XCircle, RotateCcw } from 'lucide-react';
import {
  getStatusInfo,
  formatDuration,
  isUpdateInProgress,
} from '../../api/updates';
import type { UpdateProgressResponse } from '../../api/updates';

interface UpdateProgressProps {
  progress: UpdateProgressResponse;
  onRollback?: () => void;
  rollbackLoading?: boolean;
}

export default function UpdateProgress({
  progress,
  onRollback,
  rollbackLoading = false,
}: UpdateProgressProps) {
  const percent = progress.progress_percent;
  const currentStep = progress.current_step || 'Initializing...';
  const statusInfo = getStatusInfo(progress.status);
  const inProgress = isUpdateInProgress(progress.status);

  // Calculate elapsed time
  const startedAt = new Date(progress.started_at);
  const elapsed = Math.floor((Date.now() - startedAt.getTime()) / 1000);

  return (
    <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
      {/* Header with status */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {inProgress ? (
            <Loader2 className="w-5 h-5 text-sky-500 animate-spin" />
          ) : progress.status === 'completed' ? (
            <CheckCircle className="w-5 h-5 text-emerald-500" />
          ) : progress.status === 'failed' ? (
            <XCircle className="w-5 h-5 text-rose-500" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          )}
          <div>
            <span className="font-medium text-white">System Update</span>
            <span className={`ml-2 text-sm ${statusInfo.color}`}>
              {statusInfo.icon} {statusInfo.label}
            </span>
          </div>
        </div>

        {/* Rollback button (only when failed or completed) */}
        {progress.can_rollback && onRollback && !inProgress && (
          <button
            onClick={onRollback}
            disabled={rollbackLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            {rollbackLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RotateCcw className="w-4 h-4" />
            )}
            Rollback
          </button>
        )}
      </div>

      {/* Version transition */}
      <div className="flex items-center gap-3 mb-4 p-3 bg-slate-700/50 rounded-lg">
        <div className="flex-1">
          <span className="text-xs text-slate-400 block">From</span>
          <span className="font-mono text-white">{progress.from_version}</span>
        </div>
        <div className="text-slate-500">→</div>
        <div className="flex-1">
          <span className="text-xs text-slate-400 block">To</span>
          <span className="font-mono text-sky-400">{progress.to_version}</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-sm text-slate-400">Progress</span>
          <span className="text-sm font-medium text-sky-400">{percent}%</span>
        </div>
        <div className="w-full h-3 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              progress.status === 'failed'
                ? 'bg-gradient-to-r from-rose-600 to-rose-400'
                : progress.status === 'completed'
                ? 'bg-gradient-to-r from-emerald-600 to-emerald-400'
                : 'bg-gradient-to-r from-sky-600 to-sky-400'
            }`}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Current step */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-slate-400">
          <span>Status:</span>
          <span className="text-white">{currentStep}</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="w-4 h-4" />
          <span>{formatDuration(elapsed)} elapsed</span>
        </div>
      </div>

      {/* Error message */}
      {progress.error_message && (
        <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg">
          <div className="flex items-start gap-2 text-rose-400">
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span className="text-sm">{progress.error_message}</span>
          </div>
        </div>
      )}
    </div>
  );
}
