/**
 * Chunked file upload client.
 *
 * Files >= CHUNKED_THRESHOLD are uploaded in fixed-size chunks so that
 * neither the browser nor the backend buffer the entire file in RAM.
 *
 * Protocol:
 *   1. POST /api/files/upload/chunked/init     → { upload_id, chunk_size }
 *   2. POST /api/files/upload/chunked/{id}/chunk (per chunk)
 *   3. POST /api/files/upload/chunked/{id}/complete
 *   4. DELETE /api/files/upload/chunked/{id}    (abort)
 */

import { buildApiUrl } from './api';

/** Files >= 50 MB use chunked upload. */
export const CHUNKED_THRESHOLD = 50 * 1024 * 1024;

export interface ChunkedUploadProgress {
  uploadId: string;
  filename: string;
  totalBytes: number;
  uploadedBytes: number;
  /** 0–100 */
  percentage: number;
  status: 'pending' | 'uploading' | 'completed' | 'failed';
  error?: string;
  /** bytes per second (smoothed) */
  speed: number;
  /** estimated seconds remaining */
  etaSeconds: number;
}

export type ProgressCallback = (progress: ChunkedUploadProgress) => void;

function getToken(): string | null {
  return localStorage.getItem('token');
}

/**
 * Upload a single large file using the chunked upload protocol.
 */
export class ChunkedUploader {
  private file: File;
  private targetPath: string;
  private onProgress: ProgressCallback;
  private _uploadId: string | null = null;
  private _aborted = false;
  /** Controller for the currently in-flight chunk request. */
  private _currentController: AbortController | null = null;

  /** Max retries per chunk on transient failure. */
  private maxRetries = 3;

  constructor(
    file: File,
    targetPath: string,
    onProgress: ProgressCallback,
  ) {
    this.file = file;
    this.targetPath = targetPath;
    this.onProgress = onProgress;
  }

  get uploadId(): string | null {
    return this._uploadId;
  }

  /**
   * Run the upload. Resolves when complete, rejects on unrecoverable error.
   */
  async upload(): Promise<{ path: string; size: number }> {
    const token = getToken();
    if (!token) throw new Error('Not authenticated');

    // 1. Init session
    const initController = new AbortController();
    this._currentController = initController;

    const initRes = await fetch(buildApiUrl('/api/files/upload/chunked/init'), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename: this.file.name,
        total_size: this.file.size,
        target_path: this.targetPath,
      }),
      signal: initController.signal,
    });

    if (!initRes.ok) {
      const err = await initRes.json().catch(() => ({ detail: `HTTP ${initRes.status}` }));
      throw new Error(err.detail || `Init failed: HTTP ${initRes.status}`);
    }

    const { upload_id, chunk_size } = await initRes.json();
    this._uploadId = upload_id;

    // 2. Send chunks — one per-chunk AbortController to avoid signal listener accumulation
    const totalChunks = Math.ceil(this.file.size / chunk_size);
    let uploadedBytes = 0;
    const startTime = Date.now();

    for (let i = 0; i < totalChunks; i++) {
      if (this._aborted) break;

      const start = i * chunk_size;
      const end = Math.min(start + chunk_size, this.file.size);
      const blob = this.file.slice(start, end);

      let success = false;
      let lastError: Error | null = null;

      for (let attempt = 0; attempt < this.maxRetries; attempt++) {
        if (this._aborted) break;

        try {
          // Fresh controller per attempt — no shared signal accumulation
          const chunkController = new AbortController();
          this._currentController = chunkController;

          // Send raw blob body — the browser can stream it directly from disk
          // without the multipart/form-data in-memory encoding overhead.
          const chunkUrl = buildApiUrl(
            `/api/files/upload/chunked/${upload_id}/chunk?chunk_index=${i}`,
          );
          const chunkRes = await fetch(chunkUrl, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/octet-stream',
              'X-Chunk-Index': String(i),
            },
            body: blob,
            signal: chunkController.signal,
          });

          if (!chunkRes.ok) {
            const err = await chunkRes.json().catch(() => ({ detail: `HTTP ${chunkRes.status}` }));
            throw new Error(err.detail || `Chunk ${i} failed: HTTP ${chunkRes.status}`);
          }

          const { received_bytes } = await chunkRes.json();
          uploadedBytes = received_bytes;
          success = true;

          // Let the controller be GC'd
          this._currentController = null;
          break;
        } catch (e: any) {
          // If aborted, do not retry
          if (e.name === 'AbortError' || this._aborted) throw e;
          lastError = e;
          // Wait before retry (exponential backoff)
          if (attempt < this.maxRetries - 1) {
            await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
          }
        }
      }

      if (!success) {
        // All retries exhausted — abort the server session
        await this._abortServer(token, upload_id);
        throw lastError || new Error(`Chunk ${i} failed after ${this.maxRetries} retries`);
      }

      // Report progress
      const elapsed = (Date.now() - startTime) / 1000;
      const speed = elapsed > 0 ? uploadedBytes / elapsed : 0;
      const remaining = this.file.size - uploadedBytes;
      const eta = speed > 0 ? remaining / speed : 0;

      this.onProgress({
        uploadId: upload_id,
        filename: this.file.name,
        totalBytes: this.file.size,
        uploadedBytes,
        percentage: (uploadedBytes / this.file.size) * 100,
        status: 'uploading',
        speed,
        etaSeconds: eta,
      });
    }

    if (this._aborted) {
      await this._abortServer(token, upload_id);
      throw new Error('Upload aborted');
    }

    // 3. Complete
    const completeController = new AbortController();
    this._currentController = completeController;

    const completeRes = await fetch(
      buildApiUrl(`/api/files/upload/chunked/${upload_id}/complete`),
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        signal: completeController.signal,
      },
    );

    if (!completeRes.ok) {
      const err = await completeRes.json().catch(() => ({ detail: `HTTP ${completeRes.status}` }));
      throw new Error(err.detail || `Complete failed: HTTP ${completeRes.status}`);
    }

    const result = await completeRes.json();

    this.onProgress({
      uploadId: upload_id,
      filename: this.file.name,
      totalBytes: this.file.size,
      uploadedBytes: this.file.size,
      percentage: 100,
      status: 'completed',
      speed: 0,
      etaSeconds: 0,
    });

    this._currentController = null;
    return { path: result.path, size: result.size };
  }

  /**
   * Abort an in-progress upload.
   */
  abort(): void {
    this._aborted = true;
    this._currentController?.abort();
    this._currentController = null;
  }

  private async _abortServer(token: string, uploadId: string): Promise<void> {
    try {
      await fetch(buildApiUrl(`/api/files/upload/chunked/${uploadId}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // Best effort — ignore errors during abort cleanup
    }
  }
}
