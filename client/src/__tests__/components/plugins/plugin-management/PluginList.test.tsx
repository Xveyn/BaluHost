// PluginList.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
// stub the card so this test targets only PluginList's own branching
vi.mock('../../../../components/plugins/plugin-management/PluginListCard', () => ({
  PluginListCard: ({ plugin }: { plugin: PluginInfo }) => <div data-testid="card">{plugin.name}</div>,
}));
import { PluginList } from '../../../../components/plugins/plugin-management/PluginList';

const p = (name: string): PluginInfo => ({
  name, version: '1', display_name: name, description: '', author: '', category: 'general',
  required_permissions: [], dangerous_permissions: [], is_enabled: false, has_ui: false, has_routes: false,
});

describe('PluginList', () => {
  it('renders the empty-state when there are no plugins', () => {
    render(<PluginList plugins={[]} selectedName={null} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('empty.noPlugins')).toBeInTheDocument();
    expect(screen.queryByTestId('card')).not.toBeInTheDocument();
  });

  it('renders one card per plugin when the list is non-empty', () => {
    render(<PluginList plugins={[p('a'), p('b')]} selectedName="a" actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getAllByTestId('card')).toHaveLength(2);
    expect(screen.queryByText('empty.noPlugins')).not.toBeInTheDocument();
  });
});
