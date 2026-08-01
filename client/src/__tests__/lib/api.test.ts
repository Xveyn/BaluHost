/**
 * lib/api.ts — the single axios instance every request in the app goes
 * through. T3/#317 named it the riskiest untested file in the frontend, and
 * the reason is its two interceptors: they log the user out and they warn
 * about incompatible servers, from a place no feature test ever looks at.
 *
 * The interceptors are exercised through a stubbed axios ADAPTER rather than a
 * mocked axios module: that runs the real interceptor chain the app installs
 * at import time, instead of asserting a mock against itself (the tautology
 * T4/#319 flags elsewhere). No new dependency needed for that.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios';

import { API_VERSION, apiClient, buildApiUrl, extractErrorMessage, fireAuthExpired } from '../../lib/api';

type Adapter = typeof apiClient.defaults.adapter;

const originalAdapter: Adapter = apiClient.defaults.adapter;

/** Answer every request from memory, and record the config the chain built. */
function stubAdapter(overrides: Partial<AxiosResponse> = {}) {
  const seen: { config?: InternalAxiosRequestConfig } = {};
  apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
    seen.config = config;
    return {
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      ...overrides,
    } as AxiosResponse;
  }) as Adapter;
  return seen;
}

function failingAdapter(status: number) {
  apiClient.defaults.adapter = (async () => {
    throw Object.assign(new Error(`HTTP ${status}`), { response: { status } });
  }) as Adapter;
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
});

describe('buildApiUrl', () => {
  it('keeps an absolute path as-is when there is no base URL', () => {
    expect(buildApiUrl('/api/files')).toBe('/api/files');
  });

  it('adds the leading slash a relative path is missing', () => {
    // Without this the URL would resolve against the current route instead of
    // the site root — "api/files" on /admin/users becomes /admin/api/files.
    expect(buildApiUrl('api/files')).toBe('/api/files');
  });
});

describe('request interceptor', () => {
  it('attaches the stored token as a Bearer header', async () => {
    localStorage.setItem('token', 'tok-123');
    const seen = stubAdapter();

    await apiClient.get('/api/whatever');

    expect(seen.config?.headers.Authorization).toBe('Bearer tok-123');
  });

  it('sends no Authorization header when no token is stored', async () => {
    const seen = stubAdapter();

    await apiClient.get('/api/whatever');

    expect(seen.config?.headers.Authorization).toBeUndefined();
  });

  it('reads the token per request, not once at import', async () => {
    // The login screen imports this module before a token exists; a value
    // captured at module load would leave the whole session unauthenticated.
    const seen = stubAdapter();
    await apiClient.get('/api/before-login');
    expect(seen.config?.headers.Authorization).toBeUndefined();

    localStorage.setItem('token', 'fresh');
    const after = stubAdapter();
    await apiClient.get('/api/after-login');

    expect(after.config?.headers.Authorization).toBe('Bearer fresh');
  });
});

describe('server version check', () => {
  it('fires api:upgrade-required when the server demands a newer client', async () => {
    const listener = vi.fn();
    window.addEventListener('api:upgrade-required', listener);
    stubAdapter({ headers: { 'x-api-min-version': String(Number(API_VERSION) + 1) } as AxiosResponse['headers'] });

    await apiClient.get('/api/whatever');
    window.removeEventListener('api:upgrade-required', listener);

    expect(listener).toHaveBeenCalledTimes(1);
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail;
    expect(detail).toEqual({
      serverMin: String(Number(API_VERSION) + 1),
      clientVersion: API_VERSION,
    });
  });

  it('stays quiet when the server accepts this client version', async () => {
    const listener = vi.fn();
    window.addEventListener('api:upgrade-required', listener);
    stubAdapter({ headers: { 'x-api-min-version': API_VERSION } as AxiosResponse['headers'] });

    await apiClient.get('/api/whatever');
    window.removeEventListener('api:upgrade-required', listener);

    expect(listener).not.toHaveBeenCalled();
  });

  it('stays quiet when the header is absent', async () => {
    const listener = vi.fn();
    window.addEventListener('api:upgrade-required', listener);
    stubAdapter();

    await apiClient.get('/api/whatever');
    window.removeEventListener('api:upgrade-required', listener);

    expect(listener).not.toHaveBeenCalled();
  });
});

describe('401 handling', () => {
  it('drops the token and announces the expiry', async () => {
    localStorage.setItem('token', 'stale');
    const listener = vi.fn();
    window.addEventListener('auth:expired', listener);
    failingAdapter(401);

    await expect(apiClient.get('/api/whatever')).rejects.toThrow();
    window.removeEventListener('auth:expired', listener);

    expect(localStorage.getItem('token')).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('leaves the session alone on any other error status', async () => {
    // A 500 from one endpoint must not log the user out - that would turn a
    // backend hiccup into "you have been signed out".
    localStorage.setItem('token', 'good');
    const listener = vi.fn();
    window.addEventListener('auth:expired', listener);
    failingAdapter(500);

    await expect(apiClient.get('/api/whatever')).rejects.toThrow();
    window.removeEventListener('auth:expired', listener);

    expect(localStorage.getItem('token')).toBe('good');
    expect(listener).not.toHaveBeenCalled();
  });

  it('still rejects, so callers see the failure', async () => {
    failingAdapter(401);

    await expect(apiClient.get('/api/whatever')).rejects.toThrow('HTTP 401');
  });
});

describe('fireAuthExpired', () => {
  it('clears the token and dispatches the event', () => {
    localStorage.setItem('token', 'x');
    const listener = vi.fn();
    window.addEventListener('auth:expired', listener);

    fireAuthExpired();
    window.removeEventListener('auth:expired', listener);

    expect(localStorage.getItem('token')).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('extractErrorMessage', () => {
  it('passes a plain string through', () => {
    expect(extractErrorMessage('Disk is full', 'fallback')).toBe('Disk is full');
  });

  it('joins a FastAPI validation list', () => {
    const detail = [{ msg: 'field required' }, { msg: 'not an integer' }];

    expect(extractErrorMessage(detail, 'fallback')).toBe('field required; not an integer');
  });

  it('stringifies list entries that carry no msg', () => {
    expect(extractErrorMessage(['boom'], 'fallback')).toBe('boom');
  });

  it('falls back for an empty list', () => {
    expect(extractErrorMessage([], 'fallback')).toBe('fallback');
  });

  it.each([
    ['an object', { detail: 'nested' }],
    ['null', null],
    ['undefined', undefined],
    ['a number', 42],
  ])('falls back for %s', (_label, detail) => {
    expect(extractErrorMessage(detail, 'fallback')).toBe('fallback');
  });
});

describe('module-load configuration', () => {
  /**
   * baseURL, isTauri and API_BASE_URL are resolved once at import time, so
   * they can only be observed by re-importing the module with a different
   * global in place. That is exactly the Tauri Companion's contract: its Rust
   * shell injects window.__BALU_API_BASE__ before the bundle loads.
   */
  const load = async (base?: string) => {
    vi.resetModules();
    if (base === undefined) {
      delete (window as { __BALU_API_BASE__?: string }).__BALU_API_BASE__;
    } else {
      (window as { __BALU_API_BASE__?: string }).__BALU_API_BASE__ = base;
    }
    return import('../../lib/api');
  };

  afterEach(async () => {
    await load(undefined);
  });

  it('routes through the injected proxy inside the Tauri shell', async () => {
    const api = await load('http://127.0.0.1:7788/api');

    expect(api.isTauri).toBe(true);
    expect(api.API_BASE_URL).toBe('http://127.0.0.1:7788/api');
    expect(api.apiClient.defaults.baseURL).toBe('http://127.0.0.1:7788/api');
  });

  it('prefixes both absolute and relative paths with that base', async () => {
    const api = await load('http://127.0.0.1:7788/api');

    expect(api.buildApiUrl('/files')).toBe('http://127.0.0.1:7788/api/files');
    expect(api.buildApiUrl('files')).toBe('http://127.0.0.1:7788/api/files');
  });

  it('is not a Tauri build without the injected global', async () => {
    const api = await load(undefined);

    expect(api.isTauri).toBe(false);
    expect(api.buildApiUrl('/files')).toBe('/files');
  });
});
