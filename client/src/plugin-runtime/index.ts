// Boots inside the sandbox iframe: wires postMessage, exposes the full
// window.BaluHost (React + ui + icons + utils + proxied api/toast/storage/
// navigate), applies theme tokens, then MOUNTS the plugin component.
import './runtime.css';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { createSandboxSdk } from './sdk';
import { buildSurface } from './surface';

const RUNTIME_ABI = 1;

const sdk = createSandboxSdk((msg) => window.parent.postMessage(msg, '*'));

function applyTheme(theme: unknown): void {
  const tokens = (theme as { tokens?: Record<string, string> })?.tokens;
  if (!tokens) return;
  const root = document.documentElement;
  for (const [k, v] of Object.entries(tokens)) root.style.setProperty(k, v);
}

window.addEventListener('message', (ev) => {
  const data = ev.data;
  if (data && data.kind === 'rpc-result') sdk._receive(data);
  if (data && data.kind === 'push' && data.name === 'theme-changed') applyTheme(data.payload);
  if (data && data.kind === 'push' && data.name === 'init') {
    const payload = data.payload as { user: unknown; theme?: unknown };
    applyTheme(payload.theme);
    (window as unknown as { BaluHost: unknown }).BaluHost = {
      ...buildSurface(),
      api: sdk.api,
      toast: sdk.toast,
      storage: sdk.storage,
      navigate: sdk.navigate,
      user: payload.user,
    };
    void mountPlugin(payload.user);
  }
});

async function mountPlugin(user: unknown): Promise<void> {
  // Bundle path is injected via <meta name="plugin-bundle"> in host.html.
  const meta = document.querySelector('meta[name="plugin-bundle"]') as HTMLMetaElement | null;
  const rootEl = document.getElementById('plugin-root');
  if (!meta || !rootEl) return;
  const mod = await import(/* @vite-ignore */ meta.content);
  const Component = (mod.default ?? (mod as { Plugin?: unknown }).Plugin) as
    | React.ComponentType<{ user: unknown }>
    | undefined;
  if (typeof Component !== 'function') return;
  ReactDOM.createRoot(rootEl).render(React.createElement(Component, { user }));

  // Report content height so the host can size the iframe (no inner scrollbar).
  const report = () =>
    window.parent.postMessage(
      { kind: 'event', name: 'resize', payload: { height: rootEl.scrollHeight } }, '*',
    );
  report();
  new ResizeObserver(report).observe(rootEl);
}

// Announce readiness (with our ABI) so the host responds with `init`.
window.parent.postMessage({ kind: 'event', name: 'ready', payload: { runtime_abi: RUNTIME_ABI } }, '*');
