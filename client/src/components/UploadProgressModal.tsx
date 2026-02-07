import { useTranslation } from 'react-i18next';
import { useMultiUploadProgress } from '../hooks/useUploadProgress';
import { formatBytes, formatNumber } from '../lib/formatters';

interface UploadProgressModalProps {
  uploadIds: string[] | null;
  onClose: () => void;
}

export function UploadProgressModal({ uploadIds, onClose }: UploadProgressModalProps) {
  const { t } = useTranslation(['shares']);
  const {
    progressMap,
    errors,
    overallPercentage,
    totalUploaded,
    totalSize,
    allCompleted,
    hasErrors,
  } = useMultiUploadProgress(uploadIds);

  // Auto-close on completion
  if (allCompleted && uploadIds && uploadIds.length > 0) {
    setTimeout(() => onClose(), 2000);
  }

  if (!uploadIds || uploadIds.length === 0) {
    return null;
  }


  return (
    <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-xl flex items-center justify-center z-50">
      <div className="card border-slate-800/60 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)] max-w-2xl w-full mx-4 max-h-[80vh] overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">
            {t('shares:upload.title')}
          </h2>
          {allCompleted && (
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white transition-colors"
            >
              ✕
            </button>
          )}
        </div>

        {/* Overall Progress */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-slate-300 mb-2">
            <span>{t('shares:upload.overallProgress')}</span>
            <span>{formatNumber(overallPercentage, 1)}%</span>
          </div>
          <div className="w-full bg-slate-800/60 rounded-full h-3 overflow-hidden">
            <div
              className={`h-3 rounded-full transition-all duration-300 ${
                hasErrors
                  ? 'bg-gradient-to-r from-rose-500 to-rose-600'
                  : allCompleted
                  ? 'bg-gradient-to-r from-emerald-500 to-emerald-600'
                  : 'bg-gradient-to-r from-sky-500 to-indigo-500'
              }`}
              style={{ width: `${overallPercentage}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>{formatBytes(totalUploaded)}</span>
            <span>{formatBytes(totalSize)}</span>
          </div>
        </div>

        {/* Individual File Progress */}
        <div className="space-y-3">
          {Array.from(progressMap.entries()).map(([uploadId, progress]) => {
            const error = errors.get(uploadId);
            const statusColor =
              progress.status === 'completed'
                ? 'text-emerald-400'
                : progress.status === 'failed'
                ? 'text-rose-400'
                : 'text-sky-400';

            return (
              <div
                key={uploadId}
                className="border border-slate-800/60 bg-slate-950/40 rounded-xl p-3"
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="text-sm font-medium text-slate-200 truncate flex-1">
                    {progress.filename}
                  </span>
                  <span className={`text-xs font-semibold ${statusColor} ml-2`}>
                    {progress.status === 'completed'
                      ? `✓ ${t('shares:status.done')}`
                      : progress.status === 'failed'
                      ? `✗ ${t('shares:status.failed')}`
                      : t('shares:status.uploading')}
                  </span>
                </div>

                <div className="w-full bg-slate-800/60 rounded-full h-2 mb-1 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${
                      progress.status === 'failed'
                        ? 'bg-gradient-to-r from-rose-500 to-rose-600'
                        : progress.status === 'completed'
                        ? 'bg-gradient-to-r from-emerald-500 to-emerald-600'
                        : 'bg-gradient-to-r from-sky-500 to-indigo-500'
                    }`}
                    style={{ width: `${progress.progress_percentage}%` }}
                  />
                </div>

                <div className="flex justify-between text-xs text-slate-400">
                  <span>{formatBytes(progress.uploaded_bytes)}</span>
                  <span>{formatNumber(progress.progress_percentage, 1)}%</span>
                  <span>{formatBytes(progress.total_bytes)}</span>
                </div>

                {error && (
                  <div className="mt-2 text-xs text-rose-400">
                    {t('shares:upload.error', { message: error.message })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {allCompleted && !hasErrors && (
          <div className="mt-4 text-center text-emerald-400 font-semibold">
            {t('shares:upload.allCompleted')}
          </div>
        )}

        {hasErrors && (
          <div className="mt-4 text-center text-rose-400 font-semibold">
            {t('shares:upload.someFailed')}
          </div>
        )}
      </div>
    </div>
  );
}
