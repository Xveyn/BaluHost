// client/src/__tests__/plugin-sandbox/storageBridge.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({
  apiClient: { request: vi.fn(), post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
import { apiClient } from '../../lib/api';

function makeIframe() {
  const posted: any[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}
function fireFromFrame(cw: Window, data: unknown) {
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: cw });
  window.dispatchEvent(ev);
}
const user = { id: 1, username: 'admin', role: 'admin' };
const theme = { name: 'dark', tokens: {} };

describe('PluginBridge storage channel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('storage.set maps to PUT and resolves', async () => {
    (apiClient.put as any).mockResolvedValue({ data: { ok: true } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's1', channel: 'storage', method: 'set', args: ['k', { a: 1 }] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's1')).toBeTruthy());
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/weather/_storage/k', { value: { a: 1 } });
    const res = posted.find((m: any) => m.id === 's1') as any;
    expect(res.ok).toBe(true);
    b.dispose();
  });

  it('storage.get returns the unwrapped value', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { value: 42 } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's2', channel: 'storage', method: 'get', args: ['k'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's2')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's2') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toBe(42);
    b.dispose();
  });

  it('storage.get resolves undefined on 404', async () => {
    (apiClient.get as any).mockRejectedValue({ response: { status: 404 } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's3', channel: 'storage', method: 'get', args: ['missing'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's3')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's3') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toBeUndefined();
    b.dispose();
  });

  it('storage.set rejects storage_quota on 413', async () => {
    (apiClient.put as any).mockRejectedValue({ response: { status: 413, data: { detail: 'too big' } } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's4', channel: 'storage', method: 'set', args: ['k', 'x'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's4')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's4') as any;
    expect(res.ok).toBe(false);
    expect(res.error.code).toBe('storage_quota');
    b.dispose();
  });
});
