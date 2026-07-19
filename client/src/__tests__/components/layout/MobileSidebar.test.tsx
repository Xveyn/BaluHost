import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Link, MemoryRouter } from 'react-router-dom';
import { MobileSidebar } from '../../../components/layout/MobileSidebar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));

function renderSidebar(open: boolean, onClose = vi.fn(), isImpersonating = false) {
  render(
    <MemoryRouter>
      <MobileSidebar
        open={open}
        onClose={onClose}
        isImpersonating={isImpersonating}
        items={[{ path: '/', label: 'Dash', description: 'd', icon: <span /> }]}
        adminStartIndex={-1}
        username="alice"
        isAdmin={false}
      />
    </MemoryRouter>,
  );
  return onClose;
}

describe('MobileSidebar', () => {
  it('geschlossen: -translate-x-full, kein Overlay', () => {
    renderSidebar(false);
    expect(document.body.querySelector('aside')!.className).toContain('-translate-x-full');
    expect(document.body.querySelector('div.fixed.inset-0.z-40')).toBeNull();
  });

  it('offen: translate-x-0, Overlay-Klick ruft onClose', () => {
    const onClose = renderSidebar(true);
    onClose.mockClear(); // Mount-Effekt (pathname) ruft onClose initial
    expect(document.body.querySelector('aside')!.className).toContain('translate-x-0');
    fireEvent.click(document.body.querySelector('div.fixed.inset-0.z-40')!);
    expect(onClose).toHaveBeenCalled();
  });

  it('zeigt User-Card mit Username und Rolle', () => {
    renderSidebar(true);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('User')).toBeInTheDocument();
  });

  // Regression coverage: nothing elsewhere pins these offset classes on the
  // mobile <aside> — Layout.test.tsx only asserts them on <header>/<main>, and
  // every other test here renders with isImpersonating={false} by default, so
  // dropping the prop from MobileSidebar entirely would still leave the suite green.
  it('normal: top-0 h-screen, kein Impersonation-Offset', () => {
    renderSidebar(true, vi.fn(), false);
    expect(document.body.querySelector('aside')!.className).toContain('top-0 h-screen');
    expect(document.body.querySelector('aside')!.className).not.toContain('top-10');
  });

  it('Impersonation: top-10 h-[calc(100vh-2.5rem)]', () => {
    renderSidebar(true, vi.fn(), true);
    expect(document.body.querySelector('aside')!.className).toContain('top-10 h-[calc(100vh-2.5rem)]');
    expect(document.body.querySelector('aside')!.className).not.toContain('top-0 h-screen');
  });

  it('schließt bei echter Navigation (pathname-Wechsel im Router)', () => {
    const onClose = vi.fn();
    render(
      <MemoryRouter initialEntries={['/']}>
        <Link to="/other">go</Link>
        <MobileSidebar
          open={true}
          onClose={onClose}
          isImpersonating={false}
          items={[{ path: '/', label: 'Dash', description: 'd', icon: <span /> }]}
          adminStartIndex={-1}
          username="alice"
          isAdmin={false}
        />
      </MemoryRouter>,
    );
    onClose.mockClear(); // Mount-Effekt (pathname) ruft onClose initial — siehe Test oben.
    fireEvent.click(screen.getByText('go'));
    expect(onClose).toHaveBeenCalled();
  });
});
