/**
 * BenchmarkProgress component
 *
 * Shows real-time progress during a benchmark run with:
 * - Progress bar with percentage
 * - Current test name
 * - Estimated remaining time
 * - Cancel button
 */
import { X, Clock, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatDuration } from '../../api/benchmark';
import type { BenchmarkProgressResponse } from '../../api/benchmark';

interface BenchmarkProgressProps {
  progress: BenchmarkProgressResponse;
  onCancel: () => void;
  cancelLoading: boolean;
}

export default function BenchmarkProgress({
  progress,
  onCancel,
  cancelLoading,
}: BenchmarkProgressProps) {
  const { t } = useTranslation('system');
  const percent = Math.round(progress.progress_percent);
  const currentTest = progress.current_test || t('benchmark.initializing');

  // Format remaining time
  const remainingText =
    progress.estimated_remaining_seconds !== undefined && progress.estimated_remaining_seconds !== null
      ? formatDuration(progress.estimated_remaining_seconds)
      : t('benchmark.calculating');

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Loader2 className="w-5 h-5 text-sky-500 animate-spin" />
          <span className="font-medium text-white">{t('benchmark.running')}</span>
        </div>
        <button
          onClick={onCancel}
          disabled={cancelLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-red-600 hover:bg-red-700 disabled:bg-red-800 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          {cancelLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <X className="w-4 h-4" />
          )}
          {t('benchmark.cancel')}
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-sm text-slate-400">{t('benchmark.progress')}</span>
          <span className="text-sm font-medium text-sky-400">{percent}%</span>
        </div>
        <div className="w-full h-3 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-sky-600 to-sky-400 transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Current test and remaining time */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-slate-400">
          <span>{t('benchmark.current')}:</span>
          <span className="text-white font-mono">{currentTest}</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock className="w-4 h-4" />
          <span>~{remainingText} {t('benchmark.remaining')}</span>
        </div>
      </div>
    </div>
  );
}
