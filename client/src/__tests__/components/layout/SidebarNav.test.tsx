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

  it('zeigt den Admin-Trenner exakt im Wrapper des ersten Admin-Items, direkt vor dessen Link', () => {
    renderNav();
    const separator = screen.getByText('navigation.admin');
    const usersLink = screen.getByText('Users').closest('a')!;
    const filesLink = screen.getByText('Files').closest('a')!;

    // Separator sitzt im selben Item-Wrapper wie der Users-Link (adminStartIndex=2 → Users)...
    expect(usersLink.parentElement!.contains(separator)).toBe(true);
    // ...und in DOM-Reihenfolge VOR diesem Link (isFirstAdminItem-Block steht vor <Link> im JSX).
    expect(
      separator.compareDocumentPosition(usersLink) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Das Item direkt davor (Files, nicht admin) trägt den Trenner NICHT in seinem Wrapper —
    // ein Off-by-one in isFirstAdminItem würde diese Assertion brechen.
    expect(filesLink.parentElement!.contains(separator)).toBe(false);
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

  it('mobile-Variante: inaktiver Link trägt zusätzlich hover:border-slate-800', () => {
    renderNav({ variant: 'mobile' });
    // Rendert bei Default-Pfad '/' → 'Files' ist inaktiv.
    const inactive = screen.getByText('Files').closest('a')!;
    expect(inactive.className).toContain('hover:border-slate-800');
  });

  it('desktop-Variante: inaktiver Link trägt hover:border-slate-800 NICHT', () => {
    renderNav({ variant: 'desktop' });
    const inactive = screen.getByText('Files').closest('a')!;
    expect(inactive.className).not.toContain('hover:border-slate-800');
  });
});
