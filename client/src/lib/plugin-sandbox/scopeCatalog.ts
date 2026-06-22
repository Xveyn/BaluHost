/** Core scope → concrete allowed (method, path) patterns. Curated; start small.
 *  NO write:* scopes on sensitive Core routes in v1. /api/users, /api/auth etc.
 *  appear in no entry, so no scope can ever open them. */
export const SCOPE_CATALOG: Record<string, { method: string; pattern: RegExp }[]> = {
  'read:system-info': [{ method: 'get', pattern: /^\/api\/system\/info\/?$/ }],
  'read:storage': [
    { method: 'get', pattern: /^\/api\/files\/storage(\/.*)?$/ },
    { method: 'get', pattern: /^\/api\/system\/storage(\/.*)?$/ },
  ],
  'read:power': [{ method: 'get', pattern: /^\/api\/power\/.*$/ }],
};

/** A plugin's own routes are always allowed; everything else needs a granted scope. */
export function isCallAllowed(opts: {
  pluginName: string;
  method: string;
  url: string;
  grantedScopes: string[];
}): boolean {
  const { pluginName, grantedScopes } = opts;
  const method = opts.method.toLowerCase();

  // Reject anything that isn't a clean same-origin /api/ path.
  if (!opts.url.startsWith('/api/')) return false;
  // Normalise and reject traversal.
  const path = new URL(opts.url, 'http://x').pathname;
  if (path !== opts.url.split('?')[0]) return false; // query allowed, traversal/host not
  if (path.includes('/../') || path.includes('..')) return false;

  // Own routes: /api/plugins/{thisPlugin}/...
  const ownPrefix = `/api/plugins/${pluginName}/`;
  if (path.startsWith(ownPrefix)) return true;

  // Core route: must match a granted scope's pattern.
  for (const scope of grantedScopes) {
    const entries = SCOPE_CATALOG[scope];
    if (!entries) continue;
    for (const e of entries) {
      if (e.method === method && e.pattern.test(path)) return true;
    }
  }
  return false;
}
