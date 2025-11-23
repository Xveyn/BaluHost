import { useMultiUploadProgress } from '../hooks/useUploadProgress';

interface UploadProgressModalProps {
  uploadIds: string[] | null;
  onClose: () => void;
}

export function UploadProgressModal({ uploadIds, onClose }: UploadProgressModalProps) {
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

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Uploading Files
          </h2>
          {allCompleted && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              ✕
            </button>
          )}
        </div>

        {/* Overall Progress */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400 mb-2">
            <span>Overall Progress</span>
            <span>{overallPercentage.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
            <div
              className={`h-4 rounded-full transition-all duration-300 ${
                hasErrors
                  ? 'bg-red-500'
                  : allCompleted
                  ? 'bg-green-500'
                  : 'bg-blue-500'
              }`}
              style={{ width: `${overallPercentage}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1">
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
                ? 'text-green-600 dark:text-green-400'
                : progress.status === 'failed'
                ? 'text-red-600 dark:text-red-400'
                : 'text-blue-600 dark:text-blue-400';

            return (
              <div
                key={uploadId}
                className="border border-gray-200 dark:border-gray-700 rounded-lg p-3"
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white truncate flex-1">
                    {progress.filename}
                  </span>
                  <span className={`text-xs font-semibold ${statusColor} ml-2`}>
                    {progress.status === 'completed'
                      ? '✓ Done'
                      : progress.status === 'failed'
                      ? '✗ Failed'
                      : 'Uploading...'}
                  </span>
                </div>

                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-1">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${
                      progress.status === 'failed'
                        ? 'bg-red-500'
                        : progress.status === 'completed'
                        ? 'bg-green-500'
                        : 'bg-blue-500'
                    }`}
                    style={{ width: `${progress.progress_percentage}%` }}
                  />
                </div>

                <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span>{formatBytes(progress.uploaded_bytes)}</span>
                  <span>{progress.progress_percentage.toFixed(1)}%</span>
                  <span>{formatBytes(progress.total_bytes)}</span>
                </div>

                {error && (
                  <div className="mt-2 text-xs text-red-600 dark:text-red-400">
                    Error: {error.message}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {allCompleted && !hasErrors && (
          <div className="mt-4 text-center text-green-600 dark:text-green-400 font-semibold">
            All files uploaded successfully!
          </div>
        )}

        {hasErrors && (
          <div className="mt-4 text-center text-red-600 dark:text-red-400 font-semibold">
            Some files failed to upload
          </div>
        )}
      </div>
    </div>
  );
}
