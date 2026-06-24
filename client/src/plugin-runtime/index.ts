// Boots inside the sandbox iframe: wires postMessage, exposes window.BaluHost,
// then loads the plugin bundle. (UI lib + React are added in Phase 3; here we
// expose the proxy SDK and announce readiness so the host sends `init`.)
import { createSandboxSdk } from './sdk';

const sdk = createSandboxSdk((msg) => window.parent.postMessage(msg, '*'));

window.addEventListener('message', (ev) => {
  const data = ev.data;
  if (data && data.kind === 'rpc-result') sdk._receive(data);
  if (data && data.kind === 'push' && data.name === 'init') {
    (window as unknown as { BaluHost: unknown }).BaluHost = {
      api: sdk.api, toast: sdk.toast, navigate: sdk.navigate,
      user: (data.payload as { user: unknown }).user,
    };
    void loadPluginBundle();
  }
});

async function loadPluginBundle(): Promise<void> {
  // The plugin bundle path is injected via a <meta name="plugin-bundle"> tag in host.html.
  const meta = document.querySelector('meta[name="plugin-bundle"]') as HTMLMetaElement | null;
  if (!meta) return;
  await import(/* @vite-ignore */ meta.content);
}

// Announce readiness so the host responds with `init`.
window.parent.postMessage({ kind: 'event', name: 'ready', payload: null }, '*');
