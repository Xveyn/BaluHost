import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { requestConfirmation, executeConfirmation } from '../../api/raid';

describe('raid api confirmation helpers', () => {
  const OLD_FETCH = globalThis.fetch;
  const OLD_LOCALSTORAGE = globalThis.localStorage;

  beforeEach(() => {
    // simple localStorage shim
    const store: Record<string,string> = {};
    globalThis.localStorage = {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { Object.keys(store).forEach(k => delete store[k]); },
      key: (i: number) => Object.keys(store)[i] ?? null,
      length: 0
    } as any;

    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = OLD_FETCH;
    globalThis.localStorage = OLD_LOCALSTORAGE;
    vi.restoreAllMocks();
  });

  it('requestConfirmation posts action and payload and returns token', async () => {
    (globalThis.fetch as unknown as vi.Mock).mockResolvedValueOnce(new Response(JSON.stringify({ token: 'tok-123', expires_at: 9999999999 }), { status: 200 }));
    // set token in localStorage
    localStorage.setItem('token', 'sess-token');

    const res = await requestConfirmation('delete_array', { array: 'md0' });
    expect(res).toHaveProperty('token', 'tok-123');
    expect(res).toHaveProperty('expires_at');

    // check fetch was called with expected endpoint and body
    const call = (globalThis.fetch as unknown as vi.Mock).mock.calls[0];
    expect(call[0].toString()).toContain('/api/system/raid/confirm/request');
    const options = call[1];
    expect(options.method).toBe('POST');
    const body = JSON.parse(options.body as string);
    expect(body.action).toBe('delete_array');
    expect(body.payload.array).toBe('md0');
  });

  it('executeConfirmation posts token and returns message', async () => {
    (globalThis.fetch as unknown as vi.Mock).mockResolvedValueOnce(new Response(JSON.stringify({ message: 'Executed' }), { status: 200 }));
    localStorage.setItem('token', 'sess-token');

    const res = await executeConfirmation('tok-123');
    expect(res).toHaveProperty('message', 'Executed');

    const call = (globalThis.fetch as unknown as vi.Mock).mock.calls[0];
    expect(call[0].toString()).toContain('/api/system/raid/confirm/execute');
    const options = call[1];
    expect(options.method).toBe('POST');
    const body = JSON.parse(options.body as string);
    expect(body.token).toBe('tok-123');
  });
});
