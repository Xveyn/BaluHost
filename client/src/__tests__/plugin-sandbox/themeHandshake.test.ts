// client/src/__tests__/plugin-sandbox/themeHandshake.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
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
const theme = { name: 'dark', tokens: { '--color-bg-primary': '15, 23, 42' } };

describe('PluginBridge theme handshake', () => {
  beforeEach(() => vi.clearAllMocks());

  it('includes theme in the init push', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    const init = posted.find((m: any) => m.kind === 'push' && m.name === 'init') as any;
    expect(init.payload.theme.tokens['--color-bg-primary']).toBe('15, 23, 42');
    b.dispose();
  });

  it('setTheme posts a theme-changed push', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    b.setTheme({ name: 'ocean', tokens: { '--color-bg-primary': '12, 30, 46' } });
    const changed = posted.find((m: any) => m.kind === 'push' && m.name === 'theme-changed') as any;
    expect(changed.payload.name).toBe('ocean');
    b.dispose();
  });
});
