/**
 * Upload progress tracking with Server-Sent Events (SSE)
 */

export interface UploadProgress {
  upload_id: string;
  filename: string;
  total_bytes: number;
  uploaded_bytes: number;
  status: 'uploading' | 'completed' | 'failed';
  error?: string;
  started_at?: string;
  completed_at?: string;
  progress_percentage: number;
}

export type UploadProgressCallback = (progress: UploadProgress) => void;

/**
 * Subscribe to upload progress updates via SSE
 */
export class UploadProgressStream {
  private eventSource: EventSource | null = null;
  private uploadId: string;
  private onProgress: UploadProgressCallback;
  private onError?: (error: Error) => void;

  constructor(
    uploadId: string,
    onProgress: UploadProgressCallback,
    onError?: (error: Error) => void
  ) {
    this.uploadId = uploadId;
    this.onProgress = onProgress;
    this.onError = onError;
  }

  /**
   * Start listening to upload progress
   */
  start(): void {
    const url = new URL(
      `/api/files/progress/${this.uploadId}`,
      window.location.origin
    );
    const token = localStorage.getItem('token');
    if (token) {
      url.searchParams.set('token', token);
    }

    this.eventSource = new EventSource(url.toString());

    this.eventSource.addEventListener('progress', (event) => {
      try {
        const progress: UploadProgress = JSON.parse(event.data);
        this.onProgress(progress);

        // Auto-close on completion or failure
        if (progress.status === 'completed' || progress.status === 'failed') {
          this.close();
        }
      } catch (error) {
        console.error('Failed to parse progress event:', error);
        this.onError?.(error as Error);
      }
    });

    this.eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      this.onError?.(new Error('SSE connection failed'));
      this.close();
    };
  }

  /**
   * Stop listening and close connection
   */
  close(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

/**
 * Upload progress manager for multiple files
 */
export class UploadProgressManager {
  private streams: Map<string, UploadProgressStream> = new Map();
  private progressCallbacks: Map<string, UploadProgressCallback[]> = new Map();

  /**
   * Subscribe to upload progress
   */
  subscribe(uploadId: string, callback: UploadProgressCallback): () => void {
    // Add callback to list
    if (!this.progressCallbacks.has(uploadId)) {
      this.progressCallbacks.set(uploadId, []);
    }
    this.progressCallbacks.get(uploadId)!.push(callback);

    // Create stream if not exists
    if (!this.streams.has(uploadId)) {
      const stream = new UploadProgressStream(
        uploadId,
        (progress) => {
          // Notify all callbacks
          const callbacks = this.progressCallbacks.get(uploadId) || [];
          callbacks.forEach((cb) => cb(progress));
        },
        (error) => {
          console.error(`Upload ${uploadId} error:`, error);
          this.cleanup(uploadId);
        }
      );
      stream.start();
      this.streams.set(uploadId, stream);
    }

    // Return unsubscribe function
    return () => {
      const callbacks = this.progressCallbacks.get(uploadId) || [];
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }

      // Cleanup if no more callbacks
      if (callbacks.length === 0) {
        this.cleanup(uploadId);
      }
    };
  }

  /**
   * Cleanup stream and callbacks
   */
  private cleanup(uploadId: string): void {
    const stream = this.streams.get(uploadId);
    if (stream) {
      stream.close();
      this.streams.delete(uploadId);
    }
    this.progressCallbacks.delete(uploadId);
  }

  /**
   * Close all streams
   */
  closeAll(): void {
    this.streams.forEach((stream) => stream.close());
    this.streams.clear();
    this.progressCallbacks.clear();
  }
}

// Global instance
let globalManager: UploadProgressManager | null = null;

/**
 * Get the global upload progress manager
 */
export function getUploadProgressManager(): UploadProgressManager {
  if (!globalManager) {
    globalManager = new UploadProgressManager();
  }
  return globalManager;
}
