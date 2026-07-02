import { describe, it, expect, beforeEach } from 'vitest';
import { queryPersister, persistOptions } from '../../lib/queryPersister';
import { API_VERSION } from '../../lib/api';

const emptyClient = () => ({
  timestamp: 1,
  buster: '',
  clientState: { queries: [], mutations: [] },
});

// createSyncStoragePersister's persistClient is internally throttle-wrapped
// via a real setTimeout (a macrotask, even with throttleTime: 0) and returns
// undefined rather than a promise — so `await persistClient(...)` resolves
// before the write actually lands. Flush past that macrotask before asserting.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  sessionStorage.clear();
});

describe('queryPersister', () => {
  it('persists under the baluhost-query-cache sessionStorage key', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    await flush();
    expect(sessionStorage.getItem('baluhost-query-cache')).not.toBeNull();
  });

  it('round-trips a persisted client', async () => {
    const client = emptyClient();
    client.clientState.queries = [{ queryKey: ['x'], state: { data: 42 } }] as never;
    await queryPersister.persistClient(client as never);
    await flush();
    const restored = await queryPersister.restoreClient();
    expect(restored?.clientState.queries).toHaveLength(1);
  });

  it('removeClient clears the entry', async () => {
    await queryPersister.persistClient(emptyClient() as never);
    await flush();
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
