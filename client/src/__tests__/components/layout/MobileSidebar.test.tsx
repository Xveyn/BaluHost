import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MobileSidebar } from '../../../components/layout/MobileSidebar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));

function renderSidebar(open: boolean, onClose = vi.fn()) {
  render(
    <MemoryRouter>
      <MobileSidebar
        open={open}
        onClose={onClose}
        isImpersonating={false}
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
});
