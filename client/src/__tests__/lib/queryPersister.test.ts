import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { queryPersister, persistOptions } from '../../lib/queryPersister';
import { API_VERSION } from '../../lib/api';

const emptyClient = () => ({
  timestamp: 1,
  buster: '',
  clientState: { queries: [], mutations: [] },
});

// createSyncStoragePersister's persistClient is throttle-wrapped (default
// 1000ms, trailing-edge): the write only lands once that timer fires. Fake
// timers make the flush deterministic instead of racing a real setTimeout.
beforeEach(() => {
  sessionStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('queryPersister', () => {
  it('persists under the baluhost-query-cache sessionStorage key', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    await vi.advanceTimersByTimeAsync(1000);
    expect(sessionStorage.getItem('baluhost-query-cache')).not.toBeNull();
  });

  it('round-trips a persisted client', async () => {
    const client = emptyClient();
    client.clientState.queries = [{ queryKey: ['x'], state: { data: 42 } }] as never;
    await queryPersister.persistClient(client as never);
    await vi.advanceTimersByTimeAsync(1000);
    const restored = await queryPersister.restoreClient();
    expect(restored?.clientState.queries).toHaveLength(1);
  });

  it('removeClient clears the entry', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    await vi.advanceTimersByTimeAsync(1000);
    await queryPersister.removeClient();
    const restored = await queryPersister.restoreClient();
    expect(restored).toBeUndefined();
  });
});

describe('persistOptions', () => {
  it('uses a 24h maxAge and the API_VERSION buster', () => {
    expect(persistOptions.maxAge).toBe(1000 * 60 * 60 * 24);
    expect(persistOptions.buster).toBe(API_VERSION);
  });
});
