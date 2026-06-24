// client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../../contexts/ThemeContext';
import PluginSandboxHost from '../../components/plugins/PluginSandboxHost';

// PluginBridge listens on window.addEventListener('message') — mock it so
// tests don't register real listeners (jsdom environment, no cleanup issue).
// The mock tracks how many times the constructor has been called so regression
// tests can assert "constructed once" across multiple renders.
let bridgeConstructorCallCount = 0;
let lastBridgeInstance: { start: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn>; setTheme: ReturnType<typeof vi.fn> } | null = null;

vi.mock('../../lib/plugin-sandbox/hostBridge', () => {
  class PluginBridge {
    start = vi.fn();
    dispose = vi.fn();
    setTheme = vi.fn();
    constructor() {
      bridgeConstructorCallCount++;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      lastBridgeInstance = this as any;
    }
  }
  return { PluginBridge };
});

describe('PluginSandboxHost', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };

  beforeEach(() => {
    bridgeConstructorCallCount = 0;
    lastBridgeInstance = null;
  });

  it('renders an opaque-origin sandbox iframe pointing at host.html', () => {
    const { container } = render(
      <MemoryRouter>
        <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
      </MemoryRouter>
    );
    const iframe = container.querySelector('iframe')!;
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
    expect(iframe.getAttribute('src')).toBe('/api/plugins/weather/ui/host.html');
  });

  it('never grants allow-same-origin', () => {
    const { container } = render(
      <MemoryRouter>
        <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
      </MemoryRouter>
    );
    const sandbox = container.querySelector('iframe')!.getAttribute('sandbox')!;
    expect(sandbox.includes('allow-same-origin')).toBe(false);
  });

  it('does not recreate the bridge when parent re-renders with a new [] literal (same contents) and same user', () => {
    // Render initially with one [] literal reference.
    const { rerender } = render(
      <MemoryRouter>
        <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
      </MemoryRouter>
    );

    // Capture the bridge instance created on the initial render.
    const bridgeAfterMount = lastBridgeInstance;
    expect(bridgeConstructorCallCount).toBe(1);

    // Re-render with a BRAND NEW [] literal — same contents, different reference.
    // A naïve dep array with the array object would trigger dispose+reconstruct here.
    rerender(
      <MemoryRouter>
        <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
      </MemoryRouter>
    );

    // The constructor must still have been called exactly once — no second bridge.
    expect(bridgeConstructorCallCount).toBe(1);
    // dispose() must NOT have been called between the two renders.
    expect(bridgeAfterMount!.dispose).not.toHaveBeenCalled();
  });

  it('renders the opaque-origin iframe with a ThemeProvider in the tree', () => {
    const { container } = render(
      <MemoryRouter>
        <ThemeProvider>
          <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
        </ThemeProvider>
      </MemoryRouter>
    );
    const iframe = container.querySelector('iframe')!;
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
  });
});
