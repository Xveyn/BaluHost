import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PresenceCard } from '../../../../components/power/sleep-config/PresenceCard';
import type { PresenceStatus } from '../../../../api/sleep';

const base = { presenceEnabled: true, presenceMode: 'active' as const, presenceTimeout: 3, update: vi.fn(), presenceStatus: null };

describe('PresenceCard', () => {
  it('shows mode select + timeout when enabled', () => {
    render(<PresenceCard {...base} />);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByText('sleep.presence.timeoutLabel')).toBeInTheDocument();
  });

  it('hides details when disabled', () => {
    render(<PresenceCard {...base} presenceEnabled={false} />);
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('shows the suppressing banner when presenceStatus.suppressing_suspend', () => {
    const status: PresenceStatus = { enabled: true, mode: 'active', anyone_present: true, active_session_count: 2, suppressing_suspend: true };
    render(<PresenceCard {...base} presenceStatus={status} />);
    expect(screen.getByText('sleep.presence.suppressing')).toBeInTheDocument();
  });

  it('changing mode calls update', () => {
    const update = vi.fn();
    render(<PresenceCard {...base} update={update} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'session' } });
    expect(update).toHaveBeenCalledWith({ presenceMode: 'session' });
  });
});
