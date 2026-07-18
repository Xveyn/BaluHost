import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SidebarNav } from '../../../components/layout/SidebarNav';
import type { LayoutNavItem } from '../../../components/layout/layoutNavConfig';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const items: LayoutNavItem[] = [
  { path: '/', label: 'Dash', description: 'd', icon: <span /> },
  { path: '/files', label: 'Files', description: 'f', icon: <span /> },
  { path: '/users', label: 'Users', description: 'u', icon: <span />, adminOnly: true },
  { path: '/plugins/demo', label: 'Demo', description: 'Plugin', icon: <span />, isPlugin: true },
];

function renderNav(props: Partial<React.ComponentProps<typeof SidebarNav>> = {}, path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarNav items={items} adminStartIndex={2} variant="desktop" {...props} />
    </MemoryRouter>,
  );
}

describe('SidebarNav', () => {
  it('rendert alle Items als Links', () => {
    renderNav();
    expect(screen.getAllByRole('link')).toHaveLength(4);
  });

  it('zeigt den Admin-Trenner genau vor dem ersten Admin-Item', () => {
    renderNav();
    expect(screen.getAllByText('navigation.admin')).toHaveLength(1);
  });

  it('adminStartIndex -1 → kein Trenner', () => {
    renderNav({ adminStartIndex: -1 });
    expect(screen.queryByText('navigation.admin')).not.toBeInTheDocument();
  });

  it('aktiver Link bekommt die Active-Klassen', () => {
    renderNav({}, '/files');
    const active = screen.getByText('Files').closest('a')!;
    expect(active.className).toContain('border-sky-500');
  });

  it('onNavigate feuert bei Klick auf einen Link', () => {
    const onNavigate = vi.fn();
    renderNav({ onNavigate });
    fireEvent.click(screen.getByText('Files'));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
