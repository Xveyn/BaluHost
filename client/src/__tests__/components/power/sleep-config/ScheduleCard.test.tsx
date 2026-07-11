import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { ScheduleCard } from '../../../../components/power/sleep-config/ScheduleCard';

const base = {
  scheduleEnabled: true, scheduleSleepTime: '23:00', scheduleWakeTime: '06:00',
  scheduleMode: 'soft' as const, update: vi.fn(), coreUptimeMasterOn: false, alwaysAwakeOn: false,
};

describe('ScheduleCard', () => {
  it('hides schedule detail when disabled', () => {
    render(<ScheduleCard {...base} scheduleEnabled={false} />);
    expect(screen.queryByText('Sleep at')).toBeNull();
  });

  it('shows the time inputs + mode when enabled', () => {
    render(<ScheduleCard {...base} />);
    expect(screen.getByText('Sleep at')).toBeInTheDocument();
    expect(screen.getByText('Wake at')).toBeInTheDocument();
  });

  it('shows the core-uptime override banner', () => {
    render(<ScheduleCard {...base} coreUptimeMasterOn />);
    expect(screen.getByText('sleep.coreUptime.scheduleOverride')).toBeInTheDocument();
  });

  it('shows the always-awake hint banner', () => {
    render(<ScheduleCard {...base} alwaysAwakeOn />);
    expect(screen.getByText('sleep.alwaysAwake.scheduleHint')).toBeInTheDocument();
  });

  it('editing the sleep time calls update', () => {
    const update = vi.fn();
    const { container } = render(<ScheduleCard {...base} update={update} />);
    const timeInputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(timeInputs[0], { target: { value: '22:00' } });
    expect(update).toHaveBeenCalledWith({ scheduleSleepTime: '22:00' });
  });
});
