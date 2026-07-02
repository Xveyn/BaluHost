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
  // Default throttleTime (1000ms) applies intentionally: with several
  // 1-3s-interval polling queries (CPU/memory/network/disk-io/processes),
  // an unthrottled persister would dehydrate the whole cache and hit
  // sessionStorage.setItem synchronously on every cache event.
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
