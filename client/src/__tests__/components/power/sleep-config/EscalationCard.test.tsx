import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EscalationCard } from '../../../../components/power/sleep-config/EscalationCard';

const base = { escalationEnabled: false, escalationMinutes: 60, update: vi.fn() };

describe('EscalationCard', () => {
  it('hides the minutes input when disabled', () => {
    render(<EscalationCard {...base} />);
    expect(screen.queryByText('Escalate after (min)')).toBeNull();
  });

  it('shows the minutes input when enabled and edits it', () => {
    const update = vi.fn();
    render(<EscalationCard {...base} escalationEnabled update={update} />);
    expect(screen.getByText('Escalate after (min)')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '30' } });
    expect(update).toHaveBeenCalledWith({ escalationMinutes: 30 });
  });

  it('toggle calls update with escalationEnabled', () => {
    const update = vi.fn();
    render(<EscalationCard {...base} update={update} />);
    fireEvent.click(screen.getByRole('button'));
    expect(update).toHaveBeenCalledWith({ escalationEnabled: true });
  });
});
