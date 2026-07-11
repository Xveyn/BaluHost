import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IdleDetectionCard } from '../../../../components/power/sleep-config/IdleDetectionCard';

const base = {
  autoIdleEnabled: false, idleTimeout: 15, idleCpuThreshold: 5,
  idleDiskIoThreshold: 0.5, idleHttpThreshold: 5, update: vi.fn(),
};

describe('IdleDetectionCard', () => {
  it('hides the detail inputs when disabled', () => {
    render(<IdleDetectionCard {...base} autoIdleEnabled={false} />);
    expect(screen.queryByText('Idle timeout (min)')).toBeNull();
  });

  it('shows the detail inputs when enabled', () => {
    render(<IdleDetectionCard {...base} autoIdleEnabled />);
    expect(screen.getByText('Idle timeout (min)')).toBeInTheDocument();
    expect(screen.getByText('CPU threshold (%)')).toBeInTheDocument();
  });

  it('toggling calls update with autoIdleEnabled', () => {
    const update = vi.fn();
    render(<IdleDetectionCard {...base} update={update} />);
    fireEvent.click(screen.getByRole('button'));
    expect(update).toHaveBeenCalledWith({ autoIdleEnabled: true });
  });

  it('editing a number input calls update with the field', () => {
    const update = vi.fn();
    render(<IdleDetectionCard {...base} autoIdleEnabled update={update} />);
    fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '42' } });
    expect(update).toHaveBeenCalledWith({ idleTimeout: 42 });
  });
});
