// client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PluginSandboxHost from '../../components/plugins/PluginSandboxHost';

// PluginBridge listens on window.addEventListener('message') — mock it so
// tests don't register real listeners (jsdom environment, no cleanup issue).
vi.mock('../../lib/plugin-sandbox/hostBridge', () => {
  class PluginBridge {
    start = vi.fn();
    dispose = vi.fn();
    constructor() {}
  }
  return { PluginBridge };
});

describe('PluginSandboxHost', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };

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
});
