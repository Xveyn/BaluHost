import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

vi.mock('../../hooks/useChannelStatus');
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { useChannelStatus } from '../../hooks/useChannelStatus';
import { LocalOnlyAction } from '../../components/LocalOnlyAction';

describe('<LocalOnlyAction>', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the child unchanged when channel is local', () => {
    (useChannelStatus as any).mockReturnValue({
      channel: 'local', isLocal: true, isLoading: false,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('disables the child when channel is remote', () => {
    (useChannelStatus as any).mockReturnValue({
      channel: 'remote', isLocal: false, isLoading: false,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('renders the child unchanged while loading (no flicker)', () => {
    (useChannelStatus as any).mockReturnValue({
      channel: 'remote', isLocal: false, isLoading: true,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('uses custom hint when provided', () => {
    (useChannelStatus as any).mockReturnValue({
      channel: 'remote', isLocal: false, isLoading: false,
    });
    render(
      <LocalOnlyAction hint="custom hint text">
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const wrapper = screen.getByTestId('b').parentElement;
    expect(wrapper?.getAttribute('title')).toBe('custom hint text');
  });
});
