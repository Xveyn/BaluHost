import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUpload } from '../contexts/UploadContext';
import { formatBytes, formatNumber, formatEta } from '../lib/formatters';

export function UploadProgressBar() {
  const { t } = useTranslation(['shares']);
  const { uploads, isUploading, activeCount, pendingCount, overallPercentage, abortUpload, clearCompleted } = useUpload();
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(false);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevIsUploadingRef = useRef(false);

  // Show bar when uploads exist, auto-hide 5s after all complete
  useEffect(() => {
    if (uploads.size > 0) {
      setVisible(true);
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    }

    if (!isUploading && uploads.size > 0) {
      // All done — start auto-hide timer
      hideTimerRef.current = setTimeout(() => {
        setVisible(false);
        setExpanded(false);
        clearCompleted();
      }, 5000);
    }

    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [uploads.size, isUploading, clearCompleted]);

  // Auto-expand when a new upload starts
  useEffect(() => {
    if (isUploading && !prevIsUploadingRef.current) {
      setExpanded(true);
    }
    prevIsUploadingRef.current = isUploading;
  }, [isUploading]);

  if (!visible || uploads.size === 0) return null;

  const allCompleted = !isUploading;
  const hasErrors = Array.from(uploads.values()).some(p => p.status === 'failed');
  const entries = Array.from(uploads.entries());

  // Build collapsed pill text
  const pillText = (() => {
    if (allCompleted && !hasErrors) return t('shares:upload.allCompleted');
    if (hasErrors) return t('shares:upload.someFailed');
    const parts: string[] = [];
    if (activeCount > 0) parts.push(`${activeCount} uploading`);
    if (pendingCount > 0) parts.push(`${pendingCount} ${t('shares:status.pending').toLowerCase()}`);
    return parts.join(', ') + '...';
  })();

  return (
    <div className="fixed bottom-4 right-4 z-20 w-96 max-w-[calc(100vw-2rem)]">
      {/* Collapsed pill */}
      {!expanded && (
        <button
          onClick={() => setExpanded(true)}
          className={`flex w-full items-center gap-3 rounded-2xl border px-4 py-3 shadow-lg backdrop-blur-xl transition-all ${
            hasErrors
              ? 'border-rose-500/40 bg-slate-900/90'
              : allCompleted
              ? 'border-emerald-500/40 bg-slate-900/90'
              : 'border-sky-500/40 bg-slate-900/90'
          }`}
        >
          {/* Icon */}
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-sm">
            {allCompleted && !hasErrors ? (
              <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : hasErrors ? (
              <svg className="h-4 w-4 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M12 3l9.5 16.5H2.5L12 3z" />
              </svg>
            ) : (
              <svg className="h-4 w-4 animate-pulse text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M12 3v12m0 0l-4-4m4 4l4-4" />
              </svg>
            )}
          </span>
          {/* Text */}
          <div className="flex-1 text-left">
            <p className="text-sm font-medium text-slate-200">
              {pillText}
            </p>
            {!allCompleted && (
              <div className="mt-1 h-1.5 w-full rounded-full bg-slate-800">
                <div
                  className="h-1.5 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300"
                  style={{ width: `${overallPercentage}%` }}
                />
              </div>
            )}
          </div>
          {/* Percentage */}
          {!allCompleted && (
            <span className="text-xs font-semibold text-sky-400 tabular-nums">
              {formatNumber(overallPercentage, 0)}%
            </span>
          )}
          {/* Expand icon */}
          <svg className="h-4 w-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
          </svg>
        </button>
      )}

      {/* Expanded panel */}
      {expanded && (
        <div className="rounded-2xl border border-slate-800/60 bg-slate-900/95 shadow-[0_20px_70px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800/40 px-4 py-3">
            <h3 className="text-sm font-semibold text-white">
              {t('shares:upload.title')}
            </h3>
            <div className="flex items-center gap-2">
              {allCompleted && (
                <button
                  onClick={() => {
                    clearCompleted();
                    setVisible(false);
                    setExpanded(false);
                  }}
                  className="text-xs text-slate-400 hover:text-white transition-colors"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setExpanded(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
          </div>

          {/* Overall progress */}
          <div className="px-4 py-3 border-b border-slate-800/40">
            <div className="flex justify-between text-xs text-slate-300 mb-1.5">
              <span>{t('shares:upload.overallProgress')}</span>
              <span>{formatNumber(overallPercentage, 1)}%</span>
            </div>
            <div className="w-full bg-slate-800/60 rounded-full h-2 overflow-hidden">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${
                  hasErrors
                    ? 'bg-gradient-to-r from-rose-500 to-rose-600'
                    : allCompleted
                    ? 'bg-gradient-to-r from-emerald-500 to-emerald-600'
                    : 'bg-gradient-to-r from-sky-500 to-indigo-500'
                }`}
                style={{ width: `${overallPercentage}%` }}
              />
            </div>
          </div>

          {/* Individual files */}
          <div className="max-h-64 overflow-y-auto px-4 py-2 space-y-2">
            {entries.map(([uploadId, progress]) => {
              const isPending = progress.status === 'pending';
              const statusColor =
                progress.status === 'completed'
                  ? 'text-emerald-400'
                  : progress.status === 'failed'
                  ? 'text-rose-400'
                  : isPending
                  ? 'text-slate-400'
                  : 'text-sky-400';

              return (
                <div
                  key={uploadId}
                  className="border border-slate-800/60 bg-slate-950/40 rounded-xl p-2.5"
                >
                  <div className="flex justify-between items-start mb-1.5">
                    <span className="text-xs font-medium text-slate-200 truncate flex-1">
                      {progress.filename}
                    </span>
                    <div className="flex items-center gap-2 ml-2">
                      <span className={`text-[10px] font-semibold ${statusColor}`}>
                        {progress.status === 'completed'
                          ? t('shares:status.done')
                          : progress.status === 'failed'
                          ? t('shares:status.failed')
                          : isPending
                          ? t('shares:status.pending')
                          : t('shares:status.uploading')}
                      </span>
                      {progress.status === 'uploading' && (
                        <button
                          onClick={() => abortUpload(uploadId)}
                          className="text-[10px] text-rose-400 hover:text-rose-300 transition-colors"
                          title="Abort upload"
                        >
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="w-full bg-slate-800/60 rounded-full h-1.5 mb-1 overflow-hidden">
                    <div
                      className={`h-1.5 rounded-full transition-all duration-300 ${
                        progress.status === 'failed'
                          ? 'bg-gradient-to-r from-rose-500 to-rose-600'
                          : progress.status === 'completed'
                          ? 'bg-gradient-to-r from-emerald-500 to-emerald-600'
                          : isPending
                          ? 'bg-slate-700'
                          : 'bg-gradient-to-r from-sky-500 to-indigo-500'
                      }`}
                      style={{ width: isPending ? '100%' : `${progress.percentage}%` }}
                    />
                  </div>

                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>{formatBytes(progress.uploadedBytes)}</span>
                    {progress.speed != null && progress.speed > 0 && progress.status === 'uploading' && (
                      <span className="text-sky-400">
                        {formatBytes(progress.speed)}/s
                        {progress.etaSeconds != null && progress.etaSeconds > 0 && (
                          <> · {formatEta(progress.etaSeconds)}</>
                        )}
                      </span>
                    )}
                    <span>{formatBytes(progress.totalBytes)}</span>
                  </div>

                  {progress.error && (
                    <div className="mt-1 text-[10px] text-rose-400">
                      {t('shares:upload.error', { message: progress.error })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Status footer */}
          {allCompleted && !hasErrors && (
            <div className="px-4 py-2 border-t border-slate-800/40 text-center text-xs text-emerald-400 font-semibold">
              {t('shares:upload.allCompleted')}
            </div>
          )}
          {hasErrors && (
            <div className="px-4 py-2 border-t border-slate-800/40 text-center text-xs text-rose-400 font-semibold">
              {t('shares:upload.someFailed')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
