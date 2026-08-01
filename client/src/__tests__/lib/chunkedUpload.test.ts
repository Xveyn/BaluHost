/**
 * lib/chunkedUpload.ts — the client half of the resumable upload protocol,
 * named in T3/#317 as one of the riskiest untested frontend areas. It is the
 * path every file above 50 MB takes into the NAS, and its interesting parts
 * are the ones that only happen when something goes wrong: per-chunk retry
 * with backoff, and aborting a running upload.
 *
 * `fetch` is stubbed directly rather than through MSW: the module calls four
 * endpoints with hand-built requests, so what matters is which URL, method and
 * body each step produces - not that an HTTP layer in between behaves.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { CHUNKED_THRESHOLD, ChunkedUploader, type ChunkedUploadProgress } from '../../lib/chunkedUpload';

type StubResponse = { ok: boolean; status: number; json: () => Promise<unknown> };

const ok = (body: unknown): StubResponse => ({ ok: true, status: 200, json: async () => body });
const fail = (status: number, detail?: string): StubResponse => ({
  ok: false,
  status,
  json: async () => (detail === undefined ? {} : { detail }),
});

/** A file of `size` bytes; jsdom's Blob.slice is enough for the chunk loop. */
function makeFile(size: number, name = 'big.iso'): File {
  return new File([new Uint8Array(size)], name);
}

/** URL of the nth fetch call. */
function urlOf(call: unknown[]): string {
  return String(call[0]);
}

function methodOf(call: unknown[]): string {
  return String((call[1] as RequestInit | undefined)?.method);
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('token', 'tok-abc');
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('threshold', () => {
  it('is 50 MB, the value the backend chunking is sized for', () => {
    expect(CHUNKED_THRESHOLD).toBe(50 * 1024 * 1024);
  });
});

describe('authentication', () => {
  it('refuses to start without a token, before touching the network', async () => {
    localStorage.removeItem('token');
    const uploader = new ChunkedUploader(makeFile(10), '/target', vi.fn());

    await expect(uploader.upload()).rejects.toThrow('Not authenticated');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends the token on every request of the protocol', async () => {
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 10 }))
      .mockResolvedValueOnce(ok({ received_bytes: 10 }))
      .mockResolvedValueOnce(ok({ path: '/target/big.iso', size: 10 }));

    await new ChunkedUploader(makeFile(10), '/target', vi.fn()).upload();

    for (const call of fetchMock.mock.calls) {
      const headers = (call[1] as RequestInit).headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer tok-abc');
    }
  });
});

describe('the happy path', () => {
  it('walks init -> chunk per slice -> complete', async () => {
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u7', chunk_size: 4 }))
      .mockResolvedValueOnce(ok({ received_bytes: 4 }))
      .mockResolvedValueOnce(ok({ received_bytes: 8 }))
      .mockResolvedValueOnce(ok({ received_bytes: 10 }))
      .mockResolvedValueOnce(ok({ path: '/target/big.iso', size: 10 }));

    const uploader = new ChunkedUploader(makeFile(10), '/target', vi.fn());
    const result = await uploader.upload();

    expect(fetchMock).toHaveBeenCalledTimes(5); // init + 3 chunks + complete
    expect(urlOf(fetchMock.mock.calls[0])).toContain('/api/files/upload/chunked/init');
    expect(urlOf(fetchMock.mock.calls[1])).toContain('/api/files/upload/chunked/u7/chunk?chunk_index=0');
    expect(urlOf(fetchMock.mock.calls[3])).toContain('chunk_index=2');
    expect(urlOf(fetchMock.mock.calls[4])).toContain('/api/files/upload/chunked/u7/complete');
    expect(result).toEqual({ path: '/target/big.iso', size: 10 });
    expect(uploader.uploadId).toBe('u7');
  });

  it('reports progress per chunk and a final completed state', async () => {
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 5 }))
      .mockResolvedValueOnce(ok({ received_bytes: 5 }))
      .mockResolvedValueOnce(ok({ received_bytes: 10 }))
      .mockResolvedValueOnce(ok({ path: '/p', size: 10 }));

    const seen: ChunkedUploadProgress[] = [];
    await new ChunkedUploader(makeFile(10), '/target', (p) => seen.push({ ...p })).upload();

    expect(seen.map((p) => p.status)).toEqual(['uploading', 'uploading', 'completed']);
    // Percentage follows the bytes the SERVER acknowledged, not the bytes sent.
    expect(seen.map((p) => p.percentage)).toEqual([50, 100, 100]);
    expect(seen.at(-1)).toMatchObject({ uploadedBytes: 10, totalBytes: 10, speed: 0, etaSeconds: 0 });
  });

  it('passes filename, size and target through to init', async () => {
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 99 }))
      .mockResolvedValueOnce(ok({ received_bytes: 3 }))
      .mockResolvedValueOnce(ok({ path: '/p', size: 3 }));

    await new ChunkedUploader(makeFile(3, 'holiday.mp4'), '/Shared/videos', vi.fn()).upload();

    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({
      filename: 'holiday.mp4',
      total_size: 3,
      target_path: '/Shared/videos',
    });
  });
});

describe('failures', () => {
  it('surfaces the server detail when init is refused', async () => {
    fetchMock.mockResolvedValueOnce(fail(507, 'Quota exceeded'));

    await expect(new ChunkedUploader(makeFile(10), '/t', vi.fn()).upload())
      .rejects.toThrow('Quota exceeded');
  });

  it('falls back to the status code when the error body has no detail', async () => {
    fetchMock.mockResolvedValueOnce(fail(500));

    await expect(new ChunkedUploader(makeFile(10), '/t', vi.fn()).upload())
      .rejects.toThrow('HTTP 500');
  });

  it('retries a failing chunk and carries on when it succeeds', async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 10 }))
      .mockResolvedValueOnce(fail(503, 'connection reset'))
      .mockResolvedValueOnce(ok({ received_bytes: 10 }))
      .mockResolvedValueOnce(ok({ path: '/p', size: 10 }));

    const pending = new ChunkedUploader(makeFile(10), '/t', vi.fn()).upload();
    await vi.advanceTimersByTimeAsync(5000); // let the 1s backoff elapse

    await expect(pending).resolves.toEqual({ path: '/p', size: 10 });
    expect(fetchMock).toHaveBeenCalledTimes(4); // the failed attempt is in there
  });

  it('gives up after three attempts and tells the server to drop the session', async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 10 }))
      .mockResolvedValue(fail(503, 'connection reset'));

    // The rejection lands WHILE the timers are being advanced, so the
    // expectation has to be attached first - otherwise the promise is briefly
    // unhandled and Node reports it, even though the test then handles it.
    const settled = expect(new ChunkedUploader(makeFile(10), '/t', vi.fn()).upload())
      .rejects.toThrow('connection reset');
    await vi.advanceTimersByTimeAsync(10000); // 1s + 2s backoff
    await settled;
    // init + 3 attempts + the DELETE that frees the half-written file server-side
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(methodOf(fetchMock.mock.calls[4])).toBe('DELETE');
    expect(urlOf(fetchMock.mock.calls[4])).toContain('/api/files/upload/chunked/u1');
  });

  it('does not let a failing cleanup mask the real error', async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 10 }))
      .mockResolvedValueOnce(fail(500, 'disk error'))
      .mockResolvedValueOnce(fail(500, 'disk error'))
      .mockResolvedValueOnce(fail(500, 'disk error'))
      .mockResolvedValueOnce(fail(500, 'DELETE also down'));

    const settled = expect(new ChunkedUploader(makeFile(10), '/t', vi.fn()).upload())
      .rejects.toThrow('disk error');
    await vi.advanceTimersByTimeAsync(10000);
    await settled;
  });
});

describe('abort', () => {
  it('stops between chunks and frees the server session', async () => {
    const uploader = new ChunkedUploader(makeFile(10), '/t', vi.fn());
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 5 }))
      .mockImplementationOnce(async () => {
        uploader.abort(); // between chunk 0 and chunk 1
        return ok({ received_bytes: 5 });
      })
      .mockResolvedValueOnce(ok({}));

    await expect(uploader.upload()).rejects.toThrow('Upload aborted');

    const last = fetchMock.mock.calls.at(-1)!;
    expect(methodOf(last)).toBe('DELETE');
    expect(urlOf(last)).toContain('/api/files/upload/chunked/u1');
  });

  it('sends no further chunks after an abort', async () => {
    const uploader = new ChunkedUploader(makeFile(20), '/t', vi.fn());
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 5 })) // 4 chunks
      .mockImplementationOnce(async () => {
        uploader.abort();
        return ok({ received_bytes: 5 });
      })
      .mockResolvedValue(ok({}));

    await expect(uploader.upload()).rejects.toThrow('Upload aborted');

    const chunkCalls = fetchMock.mock.calls.filter((c) => urlOf(c).includes('/chunk?'));
    expect(chunkCalls).toHaveLength(1); // not 4
  });

  it('CHARACTERISATION: an abort DURING a chunk leaves the server session behind', async () => {
    // Documents today's behaviour, it is not an endorsement. The abort path is
    // asymmetric: between chunks the loop breaks and _abortServer() runs, but a
    // mid-flight AbortError is rethrown straight out of upload() and skips the
    // DELETE, so the server keeps the partial session until it expires on its
    // own. If that is ever fixed, this test flips to expecting the DELETE.
    const uploader = new ChunkedUploader(makeFile(10), '/t', vi.fn());
    fetchMock
      .mockResolvedValueOnce(ok({ upload_id: 'u1', chunk_size: 5 }))
      .mockImplementationOnce(async () => {
        uploader.abort();
        throw Object.assign(new Error('aborted'), { name: 'AbortError' });
      });

    await expect(uploader.upload()).rejects.toThrow();

    expect(fetchMock.mock.calls.some((c) => methodOf(c) === 'DELETE')).toBe(false);
  });
});
