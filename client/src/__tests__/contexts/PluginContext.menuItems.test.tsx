import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../lib/features', () => ({ isPi: false }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ token: 'tok' }) }));
vi.mock('../../api/plugins', () => ({
  listPlugins: vi.fn(),
  getUIManifest: vi.fn(),
}));

import { PluginProvider, usePlugins } from '../../contexts/PluginContext';
import { listPlugins, getUIManifest } from '../../api/plugins';

function Probe() {
  const { pluginMenuItems } = usePlugins();
  return <div data-testid="items">{pluginMenuItems.map((i) => `${i._pluginName}:${i.id}`).join(',')}</div>;
}

const uiPlugin = (name: string, items: unknown[]) => ({
  name, display_name: name, nav_items: [], menu_items: items,
  bundle_path: 'ui/bundle.js', dashboard_widgets: [], granted_api_scopes: [],
  translations: { en: { k: 'v' } },
});

const item = (id: string, order: number) => ({
  id, icon: 'Zap', label_key: 'k', label_text: id, tone: 'neutral', order,
});

describe('PluginContext.pluginMenuItems', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listPlugins as ReturnType<typeof vi.fn>).mockResolvedValue({ plugins: [] });
  });

  it('flattens items across plugins and sorts by order', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [uiPlugin('a', [item('late', 50)]), uiPlugin('b', [item('early', 10)])],
    });

    render(<PluginProvider><Probe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('items')).toHaveTextContent('b:early,a:late'));
  });

  it('carries the plugin translations for client-side label resolution', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [uiPlugin('a', [item('one', 10)])],
    });

    function TranslationProbe() {
      const { pluginMenuItems } = usePlugins();
      return <div data-testid="tr">{JSON.stringify(pluginMenuItems[0]?._translations ?? null)}</div>;
    }

    render(<PluginProvider><TranslationProbe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('tr')).toHaveTextContent('"k":"v"'));
  });

  it('tolerates a manifest without menu_items', async () => {
    (getUIManifest as ReturnType<typeof vi.fn>).mockResolvedValue({
      plugins: [{ name: 'legacy', display_name: 'Legacy', nav_items: [] }],
    });

    render(<PluginProvider><Probe /></PluginProvider>);

    await waitFor(() => expect(screen.getByTestId('items')).toBeEmptyDOMElement());
  });
});
