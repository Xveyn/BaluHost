import { useEffect, useState } from 'react';
import { getUploadProgressManager } from '../lib/uploadProgress';
import type { UploadProgress } from '../lib/uploadProgress';

/**
 * Hook to track upload progress for a single file
 */
export function useUploadProgress(uploadId: string | null) {
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!uploadId) {
      setProgress(null);
      return;
    }

    const manager = getUploadProgressManager();
    
    const unsubscribe = manager.subscribe(uploadId, (newProgress) => {
      setProgress(newProgress);
      
      if (newProgress.status === 'failed' && newProgress.error) {
        setError(new Error(newProgress.error));
      }
    });

    return () => {
      unsubscribe();
    };
  }, [uploadId]);

  return { progress, error };
}

/**
 * Hook to track upload progress for multiple files
 */
export function useMultiUploadProgress(uploadIds: string[] | null) {
  const [progressMap, setProgressMap] = useState<Map<string, UploadProgress>>(
    new Map()
  );
  const [errors, setErrors] = useState<Map<string, Error>>(new Map());

  useEffect(() => {
    if (!uploadIds || uploadIds.length === 0) {
      setProgressMap(new Map());
      setErrors(new Map());
      return;
    }

    const manager = getUploadProgressManager();
    const unsubscribes: (() => void)[] = [];

    uploadIds.forEach((uploadId) => {
      const unsubscribe = manager.subscribe(uploadId, (newProgress) => {
        setProgressMap((prev) => {
          const next = new Map(prev);
          next.set(uploadId, newProgress);
          return next;
        });

        if (newProgress.status === 'failed' && newProgress.error) {
          setErrors((prev) => {
            const next = new Map(prev);
            next.set(uploadId, new Error(newProgress.error));
            return next;
          });
        }
      });

      unsubscribes.push(unsubscribe);
    });

    return () => {
      unsubscribes.forEach((unsub) => unsub());
    };
  }, [uploadIds]);

  // Calculate aggregate progress
  const totalProgress = Array.from(progressMap.values()).reduce(
    (acc, p) => ({
      uploaded: acc.uploaded + p.uploaded_bytes,
      total: acc.total + p.total_bytes,
    }),
    { uploaded: 0, total: 0 }
  );

  const overallPercentage =
    totalProgress.total > 0
      ? (totalProgress.uploaded / totalProgress.total) * 100
      : 0;

  const allCompleted = Array.from(progressMap.values()).every(
    (p) => p.status === 'completed' || p.status === 'failed'
  );

  const hasErrors = errors.size > 0;

  return {
    progressMap,
    errors,
    overallPercentage,
    totalUploaded: totalProgress.uploaded,
    totalSize: totalProgress.total,
    allCompleted,
    hasErrors,
  };
}
