import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PowerError, PowerEmptyState } from '../../../../components/system-monitor/power-tab/PowerStates';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, d?: string) => (typeof d === 'string' ? d : k) }) }));

describe('PowerStates', () => {
  it('PowerError shows the message', () => {
    render(<PowerError error="boom" />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });
  it('PowerEmptyState links to smart devices', () => {
    render(<MemoryRouter><PowerEmptyState /></MemoryRouter>);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/smart-devices');
    expect(screen.getByText(/No smart devices/)).toBeInTheDocument();
  });
});
