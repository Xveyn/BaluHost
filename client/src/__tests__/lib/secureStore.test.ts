import { describe, it, expect, vi, beforeEach } from 'vitest';
import { storeToken, getToken, getStoredUsername, clearToken, isAuthenticated } from '../../lib/secureStore';

// In jsdom, there's no Electron, so all calls use the sessionStorage fallback

beforeEach(() => {
  sessionStorage.clear();
});

describe('secureStore (sessionStorage fallback)', () => {
  it('stores and retrieves token', async () => {
    await storeToken('my-jwt', 'admin');

    const token = await getToken();
    expect(token).toBe('my-jwt');
  });

  it('stores and retrieves username', async () => {
    await storeToken('my-jwt', 'admin');

    const username = await getStoredUsername();
    expect(username).toBe('admin');
  });

  it('returns null when no token stored', async () => {
    expect(await getToken()).toBeNull();
    expect(await getStoredUsername()).toBeNull();
  });

  it('clears token and username', async () => {
    await storeToken('my-jwt', 'admin');
    await clearToken();

    expect(await getToken()).toBeNull();
    expect(await getStoredUsername()).toBeNull();
  });

  it('isAuthenticated returns true when token exists', async () => {
    await storeToken('my-jwt', 'admin');
    expect(await isAuthenticated()).toBe(true);
  });

  it('isAuthenticated returns false when no token', async () => {
    expect(await isAuthenticated()).toBe(false);
  });

  it('isAuthenticated returns false for empty string token', async () => {
    sessionStorage.setItem('baludesk-api-token', '');
    expect(await isAuthenticated()).toBe(false);
  });
});
