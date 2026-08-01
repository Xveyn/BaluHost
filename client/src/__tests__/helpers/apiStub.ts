/**
 * One route table, both transports.
 *
 * The frontend talks to the backend two ways: through the shared axios
 * instance (`lib/api.ts`) and through 35 hand-written `fetch()` calls that go
 * around it (F5/#307) - among them the auth check every provider tree starts
 * with (`AuthContext.tsx:70`). A test that stubs only one of them silently
 * gets a half-connected app.
 *
 * So this installs both from the same table, without pulling in a request-mock
 * framework: the axios side swaps the instance's ADAPTER, so requests still
 * run through the real interceptors (auth header, 401 handling, version
 * check) instead of past them.
 *
 * Unmatched requests answer 404 and are recorded — `missed()` turns "the
 * component renders nothing and I don't know why" into a list of the routes it
 * asked for.
 */
import { apiClient } from '../../lib/api';

export interface StubbedRoute {
  status?: number;
  /** Response body. A function receives the request body (parsed when JSON). */
  body?: unknown | ((requestBody: unknown) => unknown);
}

/** Key: "/api/path" or "POST /api/path". A bare path matches any method. */
export type ApiRoutes = Record<string, unknown | StubbedRoute>;

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
  transport: 'axios' | 'fetch';
}

function normalise(route: unknown): StubbedRoute {
  const isSpec =
    typeof route === 'object' && route !== null && ('status' in route || 'body' in route);
  return isSpec ? (route as StubbedRoute) : { status: 200, body: route };
}

function pathOf(url: string): string {
  try {
    return new URL(url, 'http://localhost').pathname;
  } catch {
    return url;
  }
}

function parseBody(raw: unknown): unknown {
  if (typeof raw !== 'string') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

export interface ApiStub {
  calls: RecordedCall[];
  /** Requests that no route matched — the first thing to look at on a blank render. */
  missed: () => RecordedCall[];
  /** Calls for one route, newest last. */
  callsTo: (path: string, method?: string) => RecordedCall[];
  restore: () => void;
}

export function installApiStub(routes: ApiRoutes = {}): ApiStub {
  const calls: RecordedCall[] = [];
  const missedCalls: RecordedCall[] = [];

  const lookup = (method: string, path: string): StubbedRoute | undefined => {
    const exact = routes[`${method.toUpperCase()} ${path}`];
    if (exact !== undefined) return normalise(exact);
    const anyMethod = routes[path];
    if (anyMethod !== undefined) return normalise(anyMethod);
    return undefined;
  };

  const resolve = (
    method: string,
    path: string,
    body: unknown,
    transport: 'axios' | 'fetch',
  ): { status: number; payload: unknown } => {
    const call: RecordedCall = { method: method.toUpperCase(), path, body, transport };
    calls.push(call);
    const route = lookup(method, path);
    if (!route) {
      missedCalls.push(call);
      return { status: 404, payload: { detail: `No stub for ${method.toUpperCase()} ${path}` } };
    }
    const payload = typeof route.body === 'function'
      ? (route.body as (b: unknown) => unknown)(body)
      : route.body;
    return { status: route.status ?? 200, payload };
  };

  const originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = (async (config) => {
    const path = pathOf(String(config.url ?? ''));
    const { status, payload } = resolve(
      String(config.method ?? 'get'),
      path,
      parseBody(config.data),
      'axios',
    );
    const response = {
      data: payload,
      status,
      statusText: status === 200 ? 'OK' : 'Error',
      headers: {},
      config,
    };
    if (status >= 400) {
      throw Object.assign(new Error(`Request failed with status code ${status}`), { response });
    }
    return response;
  }) as typeof apiClient.defaults.adapter;

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const { status, payload } = resolve(
      init?.method ?? 'GET',
      pathOf(url),
      parseBody(init?.body),
      'fetch',
    );
    return {
      ok: status < 400,
      status,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    } as Response;
  }) as typeof globalThis.fetch;

  return {
    calls,
    missed: () => missedCalls,
    callsTo: (path, method) =>
      calls.filter((c) => c.path === path && (!method || c.method === method.toUpperCase())),
    restore: () => {
      apiClient.defaults.adapter = originalAdapter;
      globalThis.fetch = originalFetch;
    },
  };
}
