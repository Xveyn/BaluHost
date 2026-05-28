import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AlwaysAwakePill } from '../../../components/topbar/pills/AlwaysAwakePill';
import type { PillState } from '../../../api/statusBar';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function base(extra: Record<string, unknown> | null, value: string): PillState {
  return { id: 'always_awake', kind: 'state', tone: 'warning', label: 'Always Awake',
           value, href: '/admin/system-control?tab=sleep', icon: 'Coffee', extra };
}

function renderPill(pill: PillState) {
  return render(<MemoryRouter><AlwaysAwakePill pill={pill} /></MemoryRouter>);
}

describe('AlwaysAwakePill', () => {
  it('renders permanent label when no expiry', () => {
    renderPill(base(null, 'permanent'));
    expect(screen.getByText('permanent')).toBeInTheDocument();
  });

  it('counts down from extra.expires_in_seconds', () => {
    renderPill(base({ expires_in_seconds: 120 }, '02:00'));
    expect(screen.getByText('02:00')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(5000); });
    expect(screen.getByText('01:55')).toBeInTheDocument();
  });
});
