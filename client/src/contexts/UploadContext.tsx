import { createContext, useContext, useState, useRef, useCallback, lazy, Suspense, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { buildApiUrl, checkFilesExist } from '../lib/api';
import { formatBytes } from '../lib/formatters';
import { ChunkedUploader, CHUNKED_THRESHOLD } from '../lib/chunkedUpload';
import type { ChunkedUploadProgress } from '../lib/chunkedUpload';

const DuplicateDialog = lazy(() => import('../components/file-manager/DuplicateDialog').then(m => ({ default: m.DuplicateDialog })));

const BATCH_MAX_FILES = 50;
const BATCH_MAX_BYTES = 200 * 1024 * 1024;

export interface DuplicateFileEntry {
  filename: string;
  size_bytes: number;
  modified_at: string;
  checksum: string | null;
}

export type DuplicateResolution = 'overwrite' | 'skip' | 'keep-both';

export interface DuplicateDecision {
  filename: string;
  resolution: DuplicateResolution;
}

interface UploadContextValue {
  uploads: Map<string, ChunkedUploadProgress>;
  isUploading: boolean;
  activeCount: number;
  pendingCount: number;
  overallPercentage: number;
  startUpload: (files: FileList, targetPath: string, availableBytes?: number | null) => void;
  abortUpload: (uploadId: string) => void;
  clearCompleted: () => void;
  onUploadsComplete: (callback: () => void) => () => void;
  /** Non-null when a duplicate dialog should be shown */
  pendingUpload: PendingUploadState | null;
  handleDuplicateResolution: (decisions: DuplicateDecision[]) => void;
  cancelDuplicateDialog: () => void;
}

interface PendingUploadState {
  files: FileList;
  targetPath: string;
  availableBytes?: number | null;
  duplicates: DuplicateFileEntry[];
}

const UploadContext = createContext<UploadContextValue | null>(null);

export function useUpload(): UploadContextValue {
  const ctx = useContext(UploadContext);
  if (!ctx) throw new Error('useUpload must be used within UploadProvider');
  return ctx;
}

export function UploadProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation(['fileManager', 'shares']);
  const [uploads, setUploads] = useState<Map<string, ChunkedUploadProgress>>(new Map());
  const activeUploadersRef = useRef<Map<string, ChunkedUploader>>(new Map());
  const completionCallbacksRef = useRef<Set<() => void>>(new Set());
  const [pendingUpload, setPendingUpload] = useState<PendingUploadState | null>(null);

  const getToken = (): string | null => {
    const token = localStorage.getItem('token');
    if (!token) toast.error('Session expired. Please sign in again.');
    return token;
  };

  const getErrorMessage = (error: any): string => {
    if (!error) return 'Unknown error';
    return error.error ?? error.detail ?? 'Unknown error';
  };

  // Derived state — 'pending' and 'uploading' both count as "active"
  const isUploading = Array.from(uploads.values()).some(
    p => p.status === 'uploading' || p.status === 'pending'
  );
  const activeCount = Array.from(uploads.values()).filter(p => p.status === 'uploading').length;
  const pendingCount = Array.from(uploads.values()).filter(p => p.status === 'pending').length;

  let totalUploaded = 0;
  let totalSize = 0;
  for (const p of uploads.values()) {
    totalUploaded += p.uploadedBytes;
    totalSize += p.totalBytes;
  }
  const overallPercentage = totalSize > 0 ? (totalUploaded / totalSize) * 100 : 0;

  const fireCompletionCallbacks = useCallback(() => {
    for (const cb of completionCallbacksRef.current) {
      try { cb(); } catch { /* ignore */ }
    }
  }, []);

  const onUploadsComplete = useCallback((callback: () => void): (() => void) => {
    completionCallbacksRef.current.add(callback);
    return () => { completionCallbacksRef.current.delete(callback); };
  }, []);

  const abortUpload = useCallback((uploadId: string) => {
    const uploader = activeUploadersRef.current.get(uploadId);
    if (uploader) {
      uploader.abort();
      activeUploadersRef.current.delete(uploadId);
    }
  }, []);

  const clearCompleted = useCallback(() => {
    setUploads(prev => {
      const next = new Map<string, ChunkedUploadProgress>();
      for (const [id, p] of prev) {
        if (p.status === 'uploading' || p.status === 'pending') next.set(id, p);
      }
      return next;
    });
  }, []);

  /**
   * Execute the actual upload logic (extracted from the old startUpload body).
   * All files in `files` will be uploaded — duplicate filtering has already happened.
   */
  const executeUpload = useCallback((files: File[], targetPath: string, availableBytes?: number | null) => {
    (async () => {
      const token = getToken();
      if (!token) return;

      // Check storage capacity
      const totalSize = files.reduce((acc, file) => acc + file.size, 0);
      if (availableBytes != null && totalSize > availableBytes) {
        toast.error(`Not enough storage space. Need ${formatBytes(totalSize)}, but only ${formatBytes(availableBytes)} available.`);
        return;
      }

      // Split files: small -> batched, large -> chunked
      const smallFiles: File[] = [];
      const largeFiles: File[] = [];
      files.forEach(file => {
        if (file.size >= CHUNKED_THRESHOLD) {
          largeFiles.push(file);
        } else {
          smallFiles.push(file);
        }
      });

      // --- Pre-register ALL uploads as pending so the overall % is accurate ---
      const totalSmallBytes = smallFiles.reduce((sum, f) => sum + f.size, 0);
      const batchProgressId = smallFiles.length > 0 ? `batch-upload-${Date.now()}` : null;

      setUploads(prev => {
        const next = new Map(prev);

        // Register batch entry for small files
        if (batchProgressId && smallFiles.length > 0) {
          next.set(batchProgressId, {
            uploadId: batchProgressId,
            filename: `Batch upload (${smallFiles.length} files)`,
            totalBytes: totalSmallBytes,
            uploadedBytes: 0,
            percentage: 0,
            status: 'pending',
            speed: 0,
            etaSeconds: 0,
          });
        }

        // Register each large file as pending
        for (const file of largeFiles) {
          const pendingId = `pending-${file.name}-${file.size}-${Date.now()}`;
          next.set(pendingId, {
            uploadId: pendingId,
            filename: file.name,
            totalBytes: file.size,
            uploadedBytes: 0,
            percentage: 0,
            status: 'pending',
            speed: 0,
            etaSeconds: 0,
          });
        }

        return next;
      });

      // --- Batched upload for small files ---
      if (smallFiles.length > 0 && batchProgressId) {
        const batches: File[][] = [];
        let currentBatch: File[] = [];
        let currentBatchSize = 0;
        for (const file of smallFiles) {
          if (currentBatch.length >= BATCH_MAX_FILES || (currentBatchSize + file.size > BATCH_MAX_BYTES && currentBatch.length > 0)) {
            batches.push(currentBatch);
            currentBatch = [];
            currentBatchSize = 0;
          }
          currentBatch.push(file);
          currentBatchSize += file.size;
        }
        if (currentBatch.length > 0) {
          batches.push(currentBatch);
        }

        let uploadedBytes = 0;
        let uploadedFiles = 0;
        let batchFailed = false;

        for (let i = 0; i < batches.length; i++) {
          const batch = batches[i];
          const batchBytes = batch.reduce((sum, f) => sum + f.size, 0);

          setUploads(prev => {
            const next = new Map(prev);
            next.set(batchProgressId, {
              uploadId: batchProgressId,
              filename: `Batch upload (${i + 1}/${batches.length}, ${uploadedFiles + batch.length}/${smallFiles.length} files)`,
              totalBytes: totalSmallBytes,
              uploadedBytes,
              percentage: totalSmallBytes > 0 ? (uploadedBytes / totalSmallBytes) * 100 : 0,
              status: 'uploading',
              speed: 0,
              etaSeconds: 0,
            });
            return next;
          });

          const formData = new FormData();
          batch.forEach(file => formData.append('files', file));
          formData.append('path', targetPath);

          try {
            const response = await fetch(buildApiUrl('/api/files/upload'), {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${token}` },
              body: formData,
            });

            if (response.ok) {
              uploadedBytes += batchBytes;
              uploadedFiles += batch.length;
            } else {
              batchFailed = true;
              let errorMsg = `HTTP ${response.status}`;
              try {
                const error = await response.json();
                errorMsg = getErrorMessage(error);
              } catch { /* use HTTP status */ }
              toast.error(`${t('fileManager:messages.uploadError')}: ${errorMsg}`);
              break;
            }
          } catch (err) {
            batchFailed = true;
            console.error('Batch upload failed:', err);
            toast.error(t('fileManager:messages.uploadError'));
            break;
          }
        }

        // Final progress update
        setUploads(prev => {
          const next = new Map(prev);
          next.set(batchProgressId, {
            uploadId: batchProgressId,
            filename: `Batch upload (${smallFiles.length} files)`,
            totalBytes: totalSmallBytes,
            uploadedBytes: batchFailed ? uploadedBytes : totalSmallBytes,
            percentage: batchFailed ? (totalSmallBytes > 0 ? (uploadedBytes / totalSmallBytes) * 100 : 0) : 100,
            status: batchFailed ? 'failed' : 'completed',
            speed: 0,
            etaSeconds: 0,
          });
          return next;
        });

        if (!batchFailed && batches.length === 1) {
          toast.success(t('fileManager:messages.uploadSuccess'));
        }
      }

      // --- Chunked upload for large files ---
      if (largeFiles.length > 0) {
        for (const file of largeFiles) {
          // Remove the pending placeholder for this file
          setUploads(prev => {
            const next = new Map(prev);
            // Find and remove the pending entry for this file
            for (const [id, p] of next) {
              if (p.status === 'pending' && p.filename === file.name && p.totalBytes === file.size) {
                next.delete(id);
                break;
              }
            }
            return next;
          });

          const uploader = new ChunkedUploader(file, targetPath, (progress) => {
            if (!activeUploadersRef.current.has(progress.uploadId)) {
              activeUploadersRef.current.set(progress.uploadId, uploader);
            }
            setUploads(prev => {
              const next = new Map(prev);
              next.set(progress.uploadId, progress);
              return next;
            });
          });

          try {
            await uploader.upload();
          } catch (err: any) {
            if (err.name !== 'AbortError') {
              console.error('Chunked upload failed:', err);
              toast.error(`${t('fileManager:messages.uploadError')}: ${err.message || 'Unknown error'}`);
            }
            if (uploader.uploadId) {
              setUploads(prev => {
                const next = new Map(prev);
                const existing = next.get(uploader.uploadId!);
                if (existing) {
                  next.set(uploader.uploadId!, { ...existing, status: 'failed', error: err.message });
                }
                return next;
              });
            }
          } finally {
            if (uploader.uploadId) {
              activeUploadersRef.current.delete(uploader.uploadId);
            }
          }
        }
      }

      // Fire completion callbacks so FileManager can reload
      fireCompletionCallbacks();
    })();
  }, [t, fireCompletionCallbacks]);

  /**
   * Start an upload: checks for duplicates first, then either shows the
   * duplicate dialog or proceeds directly to executeUpload.
   */
  const startUpload = useCallback((files: FileList, targetPath: string, availableBytes?: number | null) => {
    (async () => {
      const token = getToken();
      if (!token) return;

      const fileArray = Array.from(files);
      const filenames = fileArray.map(f => f.name);

      // Check for duplicates
      try {
        const result = await checkFilesExist(filenames, targetPath);
        if (result.duplicates.length > 0) {
          // Show duplicate dialog
          setPendingUpload({
            files,
            targetPath,
            availableBytes,
            duplicates: result.duplicates,
          });
          return;
        }
      } catch (err) {
        // If the check fails, proceed without duplicate detection
        console.warn('Duplicate check failed, proceeding with upload:', err);
      }

      // No duplicates — proceed directly
      executeUpload(fileArray, targetPath, availableBytes);
    })();
  }, [executeUpload]);

  const handleDuplicateResolution = useCallback((decisions: DuplicateDecision[]) => {
    if (!pendingUpload) return;
    const { files, targetPath, availableBytes, duplicates } = pendingUpload;
    setPendingUpload(null);

    const fileArray = Array.from(files);
    const duplicateNames = new Set(duplicates.map(d => d.filename));
    const decisionMap = new Map(decisions.map(d => [d.filename, d.resolution]));

    const filesToUpload: File[] = [];
    for (const file of fileArray) {
      if (!duplicateNames.has(file.name)) {
        // Not a duplicate — upload normally
        filesToUpload.push(file);
        continue;
      }

      const resolution = decisionMap.get(file.name) ?? 'overwrite';
      if (resolution === 'skip') {
        continue;
      } else if (resolution === 'keep-both') {
        // Rename the file: insert (1) before extension
        const dotIdx = file.name.lastIndexOf('.');
        const newName = dotIdx > 0
          ? `${file.name.slice(0, dotIdx)} (1)${file.name.slice(dotIdx)}`
          : `${file.name} (1)`;
        const renamedFile = new File([file], newName, { type: file.type, lastModified: file.lastModified });
        filesToUpload.push(renamedFile);
      } else {
        // overwrite — upload as-is
        filesToUpload.push(file);
      }
    }

    if (filesToUpload.length > 0) {
      executeUpload(filesToUpload, targetPath, availableBytes);
    }
  }, [pendingUpload, executeUpload]);

  const cancelDuplicateDialog = useCallback(() => {
    setPendingUpload(null);
  }, []);

  return (
    <UploadContext.Provider value={{
      uploads,
      isUploading,
      activeCount,
      pendingCount,
      overallPercentage,
      startUpload,
      abortUpload,
      clearCompleted,
      onUploadsComplete,
      pendingUpload,
      handleDuplicateResolution,
      cancelDuplicateDialog,
    }}>
      {children}
      {pendingUpload && (
        <Suspense fallback={null}>
          <DuplicateDialog
            duplicates={pendingUpload.duplicates}
            uploadFiles={pendingUpload.files}
            onConfirm={handleDuplicateResolution}
            onCancel={cancelDuplicateDialog}
          />
        </Suspense>
      )}
    </UploadContext.Provider>
  );
}
