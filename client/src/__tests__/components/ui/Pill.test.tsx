import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Pill } from '../../../components/ui/Pill';

function renderPill(props: Partial<React.ComponentProps<typeof Pill>> = {}) {
  return render(
    <MemoryRouter>
      <Pill tone="warning" label="RAID" value="degraded" href="/x" {...props} />
    </MemoryRouter>,
  );
}

describe('Pill', () => {
  it('renders label and value', () => {
    renderPill();
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('renders as a link to href', () => {
    renderPill({ href: '/admin/system-control?tab=raid' });
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/admin/system-control?tab=raid');
  });

  it('applies warning tone classes', () => {
    renderPill({ tone: 'warning' });
    const link = screen.getByRole('link');
    expect(link.className).toContain('amber');
  });

  it('sets an aria-label combining label and value', () => {
    renderPill({ label: 'RAID', value: 'degraded' });
    expect(screen.getByLabelText('RAID: degraded')).toBeInTheDocument();
  });

  it('flat variant uses tone text color and drops the chip border/bg', () => {
    renderPill({ tone: 'warning', flat: true });
    const link = screen.getByRole('link');
    expect(link.className).toContain('text-amber-300');
    // flat pills have no own chip border (the container provides it)
    expect(link.className).not.toContain('border');
  });
});
