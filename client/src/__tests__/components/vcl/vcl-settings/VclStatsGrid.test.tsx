import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclStatsGrid } from '../../../../components/vcl/vcl-settings/VclStatsGrid';

const overview = (over: Partial<AdminVCLOverview> = {}): AdminVCLOverview => ({
  total_versions: 1234, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
  unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
  total_users: 7, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null, ...over,
});

describe('VclStatsGrid', () => {
  it('renders the total-versions count and the active-users count', () => {
    render(<VclStatsGrid overview={overview()} totalSavings={300} savingsPercent={30} />);
    expect(screen.getByText('1,234')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });
});
