import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PillRenderer } from '../../../components/topbar/pillRenderers';
import type { PillState } from '../../../api/statusBar';

function renderPill(pill: PillState) {
  return render(<MemoryRouter><PillRenderer pill={pill} /></MemoryRouter>);
}

describe('PillRenderer', () => {
  it('renders a generic pill for a normal pill', () => {
    renderPill({ id: 'raid', kind: 'alert', tone: 'warning', label: 'RAID',
                 value: 'degraded', href: '/x', icon: 'HardDrive', extra: null });
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('routes always_awake to the countdown pill', () => {
    renderPill({ id: 'always_awake', kind: 'state', tone: 'warning', label: 'Always Awake',
                 value: '02:00', href: '/x', icon: 'Coffee',
                 extra: { variant: 'always_awake', expires_in_seconds: 120 } });
    // i18n is not initialized in component tests, so t() returns the raw key.
    expect(screen.getByText('pills.alwaysAwake.live')).toBeInTheDocument();
    expect(screen.getByText('02:00')).toBeInTheDocument();
  });
});
