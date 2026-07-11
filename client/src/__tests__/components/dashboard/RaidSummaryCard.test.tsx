import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RaidSummaryCard } from '../../../components/dashboard/RaidSummaryCard';
import type { RaidStatusResponse } from '../../../api/raid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const withArray: RaidStatusResponse = { arrays: [
  { name: 'md0', level: '1', size_bytes: 1000, status: 'clean', devices: [{ name: 'sda', state: 'active' }, { name: 'sdb', state: 'active' }], resync_progress: null },
] };

describe('RaidSummaryCard', () => {
  it('shows loading', () => {
    render(<RaidSummaryCard raidData={null} raidLoading />);
    expect(screen.getByText('raid.loading')).toBeInTheDocument();
  });
  it('shows no-arrays state', () => {
    render(<RaidSummaryCard raidData={{ arrays: [] }} raidLoading={false} />);
    expect(screen.getByText('raid.noArrays')).toBeInTheDocument();
  });
  it('renders an array with its status', () => {
    render(<RaidSummaryCard raidData={withArray} raidLoading={false} />);
    expect(screen.getByText('md0')).toBeInTheDocument();
    expect(screen.getByText('clean')).toBeInTheDocument();
  });
});
