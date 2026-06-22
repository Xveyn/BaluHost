import { describe, it, expect } from 'vitest';
import { isCallAllowed } from '../../lib/plugin-sandbox/scopeCatalog';

const base = { pluginName: 'weather', grantedScopes: [] as string[] };

describe('isCallAllowed', () => {
  it('always allows own plugin routes', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/weather/forecast' })).toBe(true);
    expect(isCallAllowed({ ...base, method: 'post', url: '/api/plugins/weather/refresh' })).toBe(true);
  });
  it('denies another plugin\'s routes', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/other/secret' })).toBe(false);
  });
  it('denies core routes without a granted scope', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/system/info' })).toBe(false);
  });
  it('allows a core route when the matching scope is granted', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'get', url: '/api/system/info' })).toBe(true);
  });
  it('still denies a different core route with that scope', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'get', url: '/api/users' })).toBe(false);
  });
  it('denies wrong method even with the scope', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'delete', url: '/api/system/info' })).toBe(false);
  });
  it('denies path traversal and non-/api/ targets', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/weather/../../users' })).toBe(false);
    expect(isCallAllowed({ ...base, method: 'get', url: 'https://evil.test/api/plugins/weather/x' })).toBe(false);
  });
});
