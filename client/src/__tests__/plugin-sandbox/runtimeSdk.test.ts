import { describe, it, expect, vi } from 'vitest';
import { createSandboxSdk } from '../../plugin-runtime/sdk';

describe('createSandboxSdk', () => {
  it('api.get posts an rpc and resolves on matching rpc-result', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.api.get('/api/plugins/weather/forecast');
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'api');
    expect(req.method).toBe('get');
    expect(req.args[0]).toBe('/api/plugins/weather/forecast');
    // simulate host reply
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { temp: 21 } });
    await expect(p).resolves.toEqual({ temp: 21 });
  });

  it('api rejects on an error rpc-result with the error code', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.api.get('/api/users');
    const req = posted.find((m) => m.kind === 'rpc');
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: false, error: { code: 'scope_denied', message: 'no' } });
    await expect(p).rejects.toMatchObject({ code: 'scope_denied' });
  });

  it('times out a pending rpc', async () => {
    vi.useFakeTimers();
    const sdk = createSandboxSdk(() => {}, { timeoutMs: 100 });
    const p = sdk.api.get('/api/plugins/weather/x');
    const assertion = expect(p).rejects.toMatchObject({ code: 'timeout' });
    await vi.advanceTimersByTimeAsync(150);
    await assertion;
    vi.useRealTimers();
  });
});
