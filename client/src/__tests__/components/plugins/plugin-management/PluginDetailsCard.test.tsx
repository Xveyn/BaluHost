import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));
import { PluginDetailsCard } from '../../../../components/plugins/plugin-management/PluginDetailsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '2.0.0', display_name: 'Demo', description: '', author: 'Jane',
  category: 'storage', dependencies: [], required_permissions: [], granted_permissions: [],
  dangerous_permissions: [], is_enabled: true, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginDetailsCard', () => {
  it('renders version and author', () => {
    render(<PluginDetailsCard plugin={detail()} />);
    expect(screen.getByText('2.0.0')).toBeInTheDocument();
    expect(screen.getByText('Jane')).toBeInTheDocument();
  });

  it('renders a homepage link only when the url is safe', () => {
    const { rerender } = render(<PluginDetailsCard plugin={detail({ homepage: 'https://example.com' })} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com/');
    rerender(<PluginDetailsCard plugin={detail({ homepage: 'javascript:alert(1)' })} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
