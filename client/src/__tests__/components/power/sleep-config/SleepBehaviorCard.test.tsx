import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SleepBehaviorCard } from '../../../../components/power/sleep-config/SleepBehaviorCard';

const base = { pauseMonitoring: true, pauseDiskIo: true, diskSpindown: true, reducedTelemetry: 30, update: vi.fn() };

describe('SleepBehaviorCard', () => {
  it('renders the three toggle rows and the interval input', () => {
    render(<SleepBehaviorCard {...base} />);
    expect(screen.getByText('Pause monitoring')).toBeInTheDocument();
    expect(screen.getByText('Pause disk I/O monitor')).toBeInTheDocument();
    expect(screen.getByText('Spin down data disks')).toBeInTheDocument();
    expect(screen.getByText('Reduced telemetry interval (s)')).toBeInTheDocument();
  });

  it('toggling "Pause monitoring" calls update', () => {
    const update = vi.fn();
    render(<SleepBehaviorCard {...base} update={update} />);
    // first toggle row button
    fireEvent.click(screen.getAllByRole('button')[0]);
    expect(update).toHaveBeenCalledWith({ pauseMonitoring: false });
  });

  it('editing the interval calls update', () => {
    const update = vi.fn();
    render(<SleepBehaviorCard {...base} update={update} />);
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '60' } });
    expect(update).toHaveBeenCalledWith({ reducedTelemetry: 60 });
  });
});
