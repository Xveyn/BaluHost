/**
 * Fallback session timings.
 *
 * These are the values `useIdleTimeout` had hardcoded before the timings became
 * admin-configurable (`auth_policy.idle_*`). They apply until the server-side
 * policy has been read — and permanently if that read fails, so a broken
 * request degrades to the previous behavior instead of to no idle logout.
 *
 * They live in their own module rather than in the hook on purpose: a test that
 * mocks `useIdleTimeout` would otherwise take the constants down with it and
 * break every other module that reads them (it did — App.routing.test.tsx).
 */
export const DEFAULT_IDLE_MS = 4 * 60 * 1000;
export const DEFAULT_WARNING_SEC = 60;
