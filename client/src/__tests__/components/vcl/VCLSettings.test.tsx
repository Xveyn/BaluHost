import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview, UserVCLStats } from '../../../types/vcl';
import type { UseVclSettingsResult } from '../../../hooks/useVclSettings';

const overview: AdminVCLOverview = {
  total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
  unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
  total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null,
};
const users: UserVCLStats[] = [{ user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500, usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic' }];

const hookValue: UseVclSettingsResult = {
  overview, storageInfo: null, users, loading: false, actionLoading: false, error: null,
  successMessage: null, editingUser: null, editForm: {}, setEditForm: vi.fn(),
  reconPreview: null, reconLoading: false, forceOverQuota: false, setForceOverQuota: vi.fn(),
  loadData: vi.fn(), handleCleanup: vi.fn(), handleScanMismatches: vi.fn(),
  handleApplyReconciliation: vi.fn(), handleEditUser: vi.fn(), handleSaveUserSettings: vi.fn(),
  setEditingUser: vi.fn(),
};
vi.mock('../../../hooks/useVclSettings', () => ({ useVclSettings: () => hookValue }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }) }));

import VCLSettings from '../../../components/vcl/VCLSettings';

describe('VCLSettings', () => {
  beforeEach(() => { Object.assign(hookValue, { loading: false, overview, users }); });

  it('renders the stats grid + user table for a populated fixture', () => {
    render(<VCLSettings />);
    expect(screen.getByText('alice')).toBeInTheDocument();           // user table
    expect(screen.getByText('Ownership Reconciliation')).toBeInTheDocument(); // recon card
  });

  it('renders none of the dashboard content while loading (early-return spinner)', () => {
    hookValue.loading = true;
    render(<VCLSettings />);
    expect(screen.queryByText('alice')).not.toBeInTheDocument();
    expect(screen.queryByText('Ownership Reconciliation')).not.toBeInTheDocument();
  });

  it('renders nothing when overview is null (and not loading)', () => {
    Object.assign(hookValue, { loading: false, overview: null });
    const { container } = render(<VCLSettings />);
    expect(container).toBeEmptyDOMElement();
  });
});
