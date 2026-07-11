import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));
import { PluginListCard } from '../../../../components/plugins/plugin-management/PluginListCard';

const base: PluginInfo = {
  name: 'demo', version: '1.2.3', display_name: 'Demo Plugin', description: 'desc',
  author: 'a', category: 'monitoring', required_permissions: [], dangerous_permissions: [],
  is_enabled: false, has_ui: false, has_routes: false,
};

describe('PluginListCard', () => {
  it('shows the enable label and the version when disabled', () => {
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('buttons.enable')).toBeInTheDocument();
    expect(screen.getByText('v1.2.3')).toBeInTheDocument();
  });

  it('shows the active badge and disable label when enabled', () => {
    render(<PluginListCard plugin={{ ...base, is_enabled: true }} isSelected={false} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('status.active')).toBeInTheDocument();
    expect(screen.getByText('buttons.disable')).toBeInTheDocument();
  });

  it('clicking the toggle fires onToggle but NOT onSelect (stopPropagation)', () => {
    const onSelect = vi.fn();
    const onToggle = vi.fn();
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={onSelect} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('buttons.enable'));
    expect(onToggle).toHaveBeenCalledWith(base);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('clicking the card body fires onSelect with the plugin name', () => {
    const onSelect = vi.fn();
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={onSelect} onToggle={() => {}} />);
    fireEvent.click(screen.getByText('Demo Plugin'));
    expect(onSelect).toHaveBeenCalledWith('demo');
  });
});
