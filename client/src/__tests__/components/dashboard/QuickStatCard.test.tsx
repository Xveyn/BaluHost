import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuickStatCard, type QuickStat } from '../../../components/dashboard/QuickStatCard';

function stat(overrides: Partial<QuickStat> = {}): QuickStat {
  return { id: 'memory', title: 'Memory', value: '8 GB', meta: 'of 16 GB', delta: { label: '+2%', tone: 'increase' }, accent: 'from-sky-500 to-indigo-500', progress: 50, icon: <svg data-testid="icon" />, ...overrides };
}

describe('QuickStatCard', () => {
  it('renders title, value, meta and delta label', () => {
    render(<QuickStatCard stat={stat({ submeta: 'DDR4' })} />);
    expect(screen.getByText('Memory')).toBeInTheDocument();
    expect(screen.getByText('8 GB')).toBeInTheDocument();
    expect(screen.getByText('of 16 GB')).toBeInTheDocument();
    expect(screen.getByText('+2%')).toBeInTheDocument();
    expect(screen.getByText('DDR4')).toBeInTheDocument();
  });

  it('fires onClick when provided', () => {
    const onClick = vi.fn();
    const { container } = render(<QuickStatCard stat={stat()} onClick={onClick} />);
    fireEvent.click(container.firstChild as Element);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render submeta line when absent', () => {
    render(<QuickStatCard stat={stat()} />);
    expect(screen.queryByText('DDR4')).not.toBeInTheDocument();
  });
});
