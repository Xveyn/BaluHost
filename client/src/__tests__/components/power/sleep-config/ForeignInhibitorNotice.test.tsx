import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { ForeignInhibitorNotice } from '../../../../components/power/sleep-config/ForeignInhibitorNotice';
import type { ForeignInhibitorStatus } from '../../../../api/sleep';

const steam: ForeignInhibitorStatus = {
  what: 'sleep:idle',
  who: 'steam-bpm-inhibit',
  why: 'Steam BPM oder Spiel aktiv',
  pid: 102863,
};

describe('ForeignInhibitorNotice', () => {
  it('renders nothing when no foreign inhibitor is held', () => {
    const { container } = render(<ForeignInhibitorNotice inhibitor={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the program and its reason', () => {
    render(<ForeignInhibitorNotice inhibitor={steam} />);
    expect(screen.getByText('steam-bpm-inhibit')).toBeInTheDocument();
    expect(screen.getByText(/Steam BPM oder Spiel aktiv/)).toBeInTheDocument();
  });

  it('shows the pid so the holder can be tracked down', () => {
    render(<ForeignInhibitorNotice inhibitor={steam} />);
    expect(screen.getByText(/102863/)).toBeInTheDocument();
  });
});
