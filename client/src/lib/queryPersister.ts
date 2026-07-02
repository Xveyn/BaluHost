import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { API_VERSION } from './api';

/**
 * Mirrors the whole TanStack Query cache to sessionStorage so it survives a full
 * page reload (F5). This is the app-wide replacement for hand-rolled sessionStorage
 * caches — tab-scoped, survives F5, cleared on tab close (sessionStorage semantics).
 */
export const queryPersister = createSyncStoragePersister({
  storage: typeof window !== 'undefined' ? window.sessionStorage : undefined,
  key: 'baluhost-query-cache',
  // Default throttleTime is 1000ms (batches persistClient calls). We write
  // immediately instead: sessionStorage writes are cheap and a throttled
  // write can be lost if the tab closes/reloads inside the throttle window,
  // which would defeat the "survives F5" purpose of this persister.
  throttleTime: 0,
});

/**
 * Passed to PersistQueryClientProvider. maxAge drops entries older than 24h on
 * hydration (per-query freshness is still driven by staleTime/refetchInterval);
 * buster invalidates every persisted cache when the API contract version changes.
 */
export const persistOptions = {
  persister: queryPersister,
  maxAge: 1000 * 60 * 60 * 24,
  buster: API_VERSION,
};
