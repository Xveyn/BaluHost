// client/src/__tests__/plugin-sandbox/hostBridge.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({
  apiClient: { request: vi.fn(async () => ({ data: { ok: true } })) },
}));
import { apiClient } from '../../lib/api';

function makeIframe() {
  const posted: unknown[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}

function fireFromFrame(contentWindow: Window, data: unknown) {
  // jsdom's MessageEvent constructor won't accept a plain object as `source`,
  // so set it explicitly after construction for the reference-equality check.
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: contentWindow });
  window.dispatchEvent(ev);
}

describe('PluginBridge', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };
  beforeEach(() => vi.clearAllMocks());

  it('sends init after the frame reports ready', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: null });
    const init = posted.find((m: any) => m.kind === 'push' && m.name === 'init') as any;
    expect(init).toBeTruthy();
    expect(init.payload.user.username).toBe('admin');
    expect(init.payload.pluginName).toBe('weather');
    b.dispose();
  });

  it('performs an allowed own-route api call and replies with the body', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 'r1', channel: 'api', method: 'get', args: ['/api/plugins/weather/forecast'] });
    await vi.waitFor(() => {
      const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r1');
      expect(res).toBeTruthy();
    });
    const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r1') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toEqual({ ok: true });
    expect(apiClient.request).toHaveBeenCalledOnce();
    b.dispose();
  });

  it('rejects a denied core-route api call without calling apiClient', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 'r2', channel: 'api', method: 'get', args: ['/api/users'] });
    await vi.waitFor(() => {
      const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r2');
      expect(res).toBeTruthy();
    });
    const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r2') as any;
    expect(res.ok).toBe(false);
    expect(res.error.code).toBe('scope_denied');
    expect(apiClient.request).not.toHaveBeenCalled();
    b.dispose();
  });

  it('ignores messages whose source is not the iframe window', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    const other = { postMessage: () => {} } as unknown as Window;
    fireFromFrame(other, { kind: 'rpc', id: 'r3', channel: 'api', method: 'get', args: ['/api/plugins/weather/x'] });
    await new Promise((r) => setTimeout(r, 10));
    expect(posted.find((m: any) => m.id === 'r3')).toBeUndefined();
    b.dispose();
  });

  it('routes resize events to onResize', () => {
    const { iframe, contentWindow } = makeIframe();
    const onResize = vi.fn();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, onResize });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'resize', payload: { height: 420 } });
    expect(onResize).toHaveBeenCalledWith(420);
    b.dispose();
  });
});
