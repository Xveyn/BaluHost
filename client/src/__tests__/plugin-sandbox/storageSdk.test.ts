import { describe, it, expect } from 'vitest';
import { createSandboxSdk } from '../../plugin-runtime/sdk';

describe('createSandboxSdk storage', () => {
  it('storage.set posts a storage rpc and resolves on result', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.storage.set('units', { t: 'C' });
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'storage');
    expect(req.method).toBe('set');
    expect(req.args).toEqual(['units', { t: 'C' }]);
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { ok: true } });
    await expect(p).resolves.toEqual({ ok: true });
  });

  it('storage.get resolves the value', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.storage.get('units');
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'storage');
    expect(req.method).toBe('get');
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { t: 'C' } });
    await expect(p).resolves.toEqual({ t: 'C' });
  });
});
