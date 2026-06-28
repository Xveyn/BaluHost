import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PluginProvider, usePlugins } from '../../contexts/PluginContext';

vi.mock('../../api/plugins', () => ({
  listPlugins: vi.fn().mockResolvedValue({ plugins: [], total: 0 }),
  getUIManifest: vi.fn().mockResolvedValue({
    plugins: [
      {
        name: 'weather',
        display_name: 'Weather',
        nav_items: [{ path: 'weather', label: 'Weather', icon: 'cloud', admin_only: false, order: 50 }],
        bundle_path: 'bundle.js',
        dashboard_widgets: [],
        granted_api_scopes: ['read:system-info'],
      },
    ],
  }),
}));

// AuthContext provides a token so PluginContext loads (mock per repo convention).
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ token: 't' }) }));
vi.mock('../../lib/features', () => ({ isPi: false }));

function Probe() {
  const { pluginNavItems } = usePlugins();
  return <div data-testid="nav">{pluginNavItems.map((n) => n.path).join(',')}</div>;
}

describe('PluginContext external nav (Gap C)', () => {
  it('renders external plugin nav item from /ui/manifest', async () => {
    render(
      <PluginProvider>
        <Probe />
      </PluginProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('nav')).toHaveTextContent('weather/weather'));
  });
});
