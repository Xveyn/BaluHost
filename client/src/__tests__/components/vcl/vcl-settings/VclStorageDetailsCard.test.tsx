import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclStorageDetailsCard } from '../../../../components/vcl/vcl-settings/VclStorageDetailsCard';

const overview = (over: Partial<AdminVCLOverview> = {}): AdminVCLOverview => ({
  total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 8,
  unique_blobs: 6, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 3, cached_versions_count: 2,
  total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null, ...over,
});

describe('VclStorageDetailsCard', () => {
  it('renders unique/total blobs and the never-cleanup fallback', () => {
    render(<VclStorageDetailsCard overview={overview()} compressionRatio={2.5} />);
    expect(screen.getByText('6 / 8')).toBeInTheDocument();
    // last_cleanup_at is null → the 'never' i18n key renders (appears twice: cleanup + priority mode)
    expect(screen.getAllByText('vcl.storageDetails.never').length).toBeGreaterThanOrEqual(1);
  });
});
