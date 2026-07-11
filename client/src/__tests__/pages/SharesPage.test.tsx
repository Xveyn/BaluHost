import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithQueryClient } from '../helpers/queryClient';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../hooks/useFileShares', () => ({ useFileShares: vi.fn() }));
vi.mock('../../hooks/useCloudExports', () => ({ useCloudExports: vi.fn() }));
vi.mock('../../api/shares', () => ({ getShareableUsers: vi.fn(), deleteFileShare: vi.fn() }));
vi.mock('../../components/CreateFileShareModal', () => ({ default: () => null }));
vi.mock('../../components/EditFileShareModal', () => ({ default: () => null }));

import { useFileShares } from '../../hooks/useFileShares';
import { useCloudExports } from '../../hooks/useCloudExports';
import { getShareableUsers } from '../../api/shares';
import type { FileShare } from '../../api/shares';
import type { CloudExportJob } from '../../api/cloud-export';
import SharesPage from '../../pages/SharesPage';

const fileShare = (over: Partial<FileShare> = {}): FileShare => ({
  id: 1, file_id: 10, owner_id: 1, shared_with_user_id: 2,
  can_read: true, can_write: false, can_delete: false, can_share: false,
  expires_at: null, created_at: '2026-01-01T00:00:00Z', last_accessed_at: null,
  is_expired: false, is_accessible: true,
  owner_username: 'alice', shared_with_username: 'bob',
  file_name: 'alpha.txt', file_path: '/alpha.txt', file_size: 0, is_directory: false,
  ...over,
});

const cloudJob = (over: Partial<CloudExportJob> = {}): CloudExportJob => ({
  id: 1, user_id: 1, connection_id: 1, source_path: '/f', file_name: 'f.zip',
  is_directory: false, file_size_bytes: 0, cloud_folder: '/', cloud_path: null,
  share_link: 'https://example.com/x', link_type: 'view', status: 'ready',
  progress_bytes: 0, error_message: null, created_at: '2026-01-01T00:00:00Z',
  completed_at: null, expires_at: null, ...over,
});

const statistics = { total_file_shares: 2, active_file_shares: 2, files_shared_with_me: 0 };

function mockFileShares(fileShares: FileShare[]) {
  (useFileShares as any).mockReturnValue({
    fileShares, sharedWithMe: [], statistics, loading: false, error: null,
  });
}
function mockCloudExports(cloudExports: CloudExportJob[]) {
  (useCloudExports as any).mockReturnValue({
    cloudExports, cloudStats: null, loading: false,
    reload: vi.fn(), revoke: vi.fn(), retry: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  (getShareableUsers as any).mockResolvedValue([]);
});

describe('SharesPage (page orchestration — F2 integration)', () => {
  it('search narrows the My Shares list (matchesFilters)', async () => {
    mockFileShares([fileShare({ id: 1, file_name: 'alpha.txt', shared_with_username: 'bob' }),
                    fileShare({ id: 2, file_name: 'beta.txt', shared_with_username: 'carol' })]);
    mockCloudExports([]);
    renderWithQueryClient(<SharesPage />);

    await waitFor(() => expect(screen.getAllByText('alpha.txt').length).toBeGreaterThan(0));
    expect(screen.getAllByText('beta.txt').length).toBeGreaterThan(0);

    fireEvent.change(screen.getByPlaceholderText('search.placeholder'), { target: { value: 'alpha' } });
    expect(screen.getAllByText('alpha.txt').length).toBeGreaterThan(0);
    expect(screen.queryByText('beta.txt')).toBeNull();
  });

  it('filtering to zero shows the "no matching" empty state, not "no shares" (allCount wiring)', async () => {
    mockFileShares([fileShare({ id: 1, file_name: 'alpha.txt' }),
                    fileShare({ id: 2, file_name: 'beta.txt' })]);
    mockCloudExports([]);
    renderWithQueryClient(<SharesPage />);

    await waitFor(() => expect(screen.getAllByText('alpha.txt').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByPlaceholderText('search.placeholder'), { target: { value: 'zzz-no-match' } });

    // allCount (2) > 0 while filtered data is empty → "noMatchingShares", NOT "noShares"
    expect(screen.getByText('empty.noMatchingShares')).toBeInTheDocument();
    expect(screen.queryByText('empty.noShares')).toBeNull();
  });

  it('provider header sort orders cloud rows via the custom getValueForSort', async () => {
    mockFileShares([]);
    // input order: OneDrive first, then Google Drive
    mockCloudExports([
      cloudJob({ id: 1, file_name: 'one.zip', share_link: 'https://1drv.ms/x' }),
      cloudJob({ id: 2, file_name: 'goog.zip', share_link: 'https://drive.google.com/x' }),
    ]);
    renderWithQueryClient(<SharesPage />);

    // switch to the Cloud Shares tab
    fireEvent.click(await screen.findByText('tabs.cloudExports'));
    await waitFor(() => expect(screen.getAllByText('Google Drive').length).toBeGreaterThan(0));

    // click the provider column header → ascending sort
    fireEvent.click(screen.getByText('shares:cloudExport.provider'));

    // desktop <td> cells only; first provider cell should now be Google Drive (asc, before OneDrive)
    const cellTexts = screen.getAllByRole('cell').map((c) => c.textContent || '');
    const gd = cellTexts.findIndex((tx) => tx.includes('Google Drive'));
    const od = cellTexts.findIndex((tx) => tx.includes('OneDrive'));
    expect(gd).toBeGreaterThanOrEqual(0);
    expect(od).toBeGreaterThanOrEqual(0);
    expect(gd).toBeLessThan(od);
  });
});
