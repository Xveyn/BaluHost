import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LayoutHeader } from '../../../components/layout/LayoutHeader';

const featureState = vi.hoisted(() => ({ isPi: false }));
vi.mock('../../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));
vi.mock('../../../components/NotificationCenter', () => ({ default: () => <div data-testid="notification-center" /> }));
vi.mock('../../../components/PowerMenu', () => ({ default: () => <div data-testid="power-menu" /> }));
vi.mock('../../../components/UserMenu', () => ({ default: () => <div data-testid="user-menu" /> }));
vi.mock('../../../components/topbar/TopbarStatusStrip', () => ({ TopbarStatusStrip: () => <div data-testid="topbar-status-strip" /> }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const props = {
  isImpersonating: false,
  isAdmin: true,
  onOpenMobileMenu: vi.fn(),
  onShutdown: vi.fn(),
  onRestart: vi.fn(),
  onLogout: vi.fn(),
};

beforeEach(() => { featureState.isPi = false; });

describe('LayoutHeader', () => {
  it('Standard: PowerMenu + NotificationCenter + StatusStrip, kein Pi-Logout-Button', () => {
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByTestId('topbar-status-strip')).toBeInTheDocument();
    expect(screen.queryByTitle('Logout')).not.toBeInTheDocument();
  });

  it('Pi: Logout-Button statt PowerMenu, kein NotificationCenter/StatusStrip', () => {
    featureState.isPi = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTitle('Logout')).toBeInTheDocument();
    expect(screen.queryByTestId('power-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('notification-center')).not.toBeInTheDocument();
    expect(screen.queryByTestId('topbar-status-strip')).not.toBeInTheDocument();
  });

  it('Impersonation: header top-10', () => {
    const { container } = render(<MemoryRouter><LayoutHeader {...props} isImpersonating /></MemoryRouter>);
    expect(container.querySelector('header')!.className).toContain('top-10');
  });
});
