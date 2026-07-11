import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginTabNav, TABS } from '../../../../components/plugins/plugin-management/PluginTabNav';

describe('PluginTabNav', () => {
  it('renders one button per tab', () => {
    render(<PluginTabNav activeTab="plugins" onSelect={() => {}} />);
    expect(screen.getAllByRole('button')).toHaveLength(TABS.length);
  });

  it('fires onSelect with the clicked tab id', () => {
    const onSelect = vi.fn();
    render(<PluginTabNav activeTab="plugins" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('tabs.marketplace'));
    expect(onSelect).toHaveBeenCalledWith('marketplace');
  });
});
