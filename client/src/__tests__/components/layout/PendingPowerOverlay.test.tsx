import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PendingPowerOverlay } from '../../../components/layout/PendingPowerOverlay';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

describe('PendingPowerOverlay', () => {
  it('rendert null, wenn action null ist', () => {
    const { container } = render(<PendingPowerOverlay action={null} message={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('restart-Variante: amber-Klassen + Restart-Label', () => {
    const { container } = render(<PendingPowerOverlay action="restart" message="Restarting — waiting for server..." />);
    const iconBox = container.querySelector('div.h-12.w-12')!;
    expect(iconBox.className).toContain('bg-amber-500/10');
    expect(iconBox.className).toContain('text-amber-400');
    expect(screen.getByText('Restarting...')).toBeInTheDocument();
  });

  it('shutdown-Variante: rose-Klassen + Shutdown-Label', () => {
    const { container } = render(<PendingPowerOverlay action="shutdown" message="Shutdown scheduled — stopping in ~3s" />);
    const iconBox = container.querySelector('div.h-12.w-12')!;
    expect(iconBox.className).toContain('bg-rose-500/10');
    expect(iconBox.className).toContain('text-rose-400');
    expect(screen.getByText('Shutting down...')).toBeInTheDocument();
  });

  it('zeigt die übergebene message an', () => {
    render(<PendingPowerOverlay action="shutdown" message="Shutdown scheduled — stopping in ~3s" />);
    expect(screen.getByText('Shutdown scheduled — stopping in ~3s')).toBeInTheDocument();
  });
});
