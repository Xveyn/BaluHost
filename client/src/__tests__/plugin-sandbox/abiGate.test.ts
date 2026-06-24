// client/src/__tests__/plugin-sandbox/abiGate.test.ts
import { describe, it, expect, vi } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({ apiClient: { request: vi.fn(), post: vi.fn() } }));

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

describe('PluginBridge ABI gate', () => {
  it('refuses init and reports abi_mismatch when runtime is too old', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const onError = vi.fn();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme, minRuntimeAbi: 2, onError });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    expect(onError).toHaveBeenCalledWith('abi_mismatch');
    expect(posted.find((m: any) => m.kind === 'push' && m.name === 'init')).toBeUndefined();
    b.dispose();
  });

  it('sends init when the runtime satisfies min_runtime_abi', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme, minRuntimeAbi: 1 });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    expect(posted.find((m: any) => m.kind === 'push' && m.name === 'init')).toBeTruthy();
    b.dispose();
  });
});
