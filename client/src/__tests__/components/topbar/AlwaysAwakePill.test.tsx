import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AlwaysAwakePill } from '../../../components/topbar/pills/AlwaysAwakePill';
import type { PillState } from '../../../api/statusBar';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function base(extra: Record<string, unknown> | null, value: string): PillState {
  return { id: 'always_awake', kind: 'state', tone: 'warning', label_key: 'pills.alwaysAwake.live',
           value, href: '/admin/system-control?tab=sleep', icon: 'Coffee', extra };
}

function renderPill(pill: PillState) {
  return render(<MemoryRouter><AlwaysAwakePill pill={pill} /></MemoryRouter>);
}

describe('AlwaysAwakePill', () => {
  // i18n is not initialized in component tests, so t() returns the raw key.
  it('renders the permanent label key when no expiry', () => {
    renderPill(base({ variant: 'always_awake' }, 'permanent'));
    expect(screen.getByText('pills.alwaysAwake.live')).toBeInTheDocument();
    expect(screen.getByText('pills.alwaysAwake.permanent')).toBeInTheDocument();
  });

  it('counts down from extra.expires_in_seconds', () => {
    renderPill(base({ variant: 'always_awake', expires_in_seconds: 120 }, '02:00'));
    expect(screen.getByText('02:00')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(5000); });
    expect(screen.getByText('01:55')).toBeInTheDocument();
  });

  it('renders the core-uptime variant with the Kernbetriebszeit label + until value', () => {
    const pill: PillState = {
      id: 'always_awake', kind: 'state', tone: 'success', label_key: 'pills.alwaysAwake.coreUptimeLive',
      value: 'bis 22:00', href: '/admin/system-control?tab=sleep', icon: 'Shield',
      extra: { variant: 'core_uptime', until: '22:00' },
    };
    renderPill(pill);
    expect(screen.getByText('pills.alwaysAwake.coreUptimeLive')).toBeInTheDocument();
    expect(screen.getByText('pills.alwaysAwake.coreUptimeUntil')).toBeInTheDocument();
  });
});
