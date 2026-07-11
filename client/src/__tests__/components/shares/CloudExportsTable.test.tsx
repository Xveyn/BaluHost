import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { CloudExportsTable } from '../../../components/shares/CloudExportsTable';
import type { CloudExportJob } from '../../../api/cloud-export';

// Full object (all required CloudExportJob fields), then override.
const job = (over: Partial<CloudExportJob> = {}): CloudExportJob => ({
  id: 1, user_id: 1, connection_id: 1, source_path: '/f.zip', file_name: 'f.zip',
  is_directory: false, file_size_bytes: 0, cloud_folder: '/', cloud_path: null,
  share_link: 'https://example.com/x', link_type: 'view', status: 'ready',
  progress_bytes: 0, error_message: null, created_at: '2026-01-01T00:00:00Z',
  completed_at: null, expires_at: null, ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };
const handlers = { onCopyLink: vi.fn(), onRevoke: vi.fn(), onRetry: vi.fn() };

describe('CloudExportsTable', () => {
  it('shows the empty state when there are no jobs', () => {
    render(<CloudExportsTable jobs={[]} {...sortProps} {...handlers} />);
    expect(screen.getByText('shares:cloudExport.noExports')).toBeInTheDocument();
  });

  it('shows Revoke (ready) but not Retry, and fires onRevoke', () => {
    const onRevoke = vi.fn();
    render(<CloudExportsTable jobs={[job({ status: 'ready' })]} {...sortProps} {...handlers} onRevoke={onRevoke} />);
    expect(screen.queryAllByTitle('shares:cloudExport.retry')).toHaveLength(0);
    fireEvent.click(screen.getAllByTitle('shares:cloudExport.revoke')[0]);
    expect(onRevoke).toHaveBeenCalledWith(1);
  });

  it('shows Retry (failed) but not Revoke, and fires onRetry', () => {
    const onRetry = vi.fn();
    render(<CloudExportsTable jobs={[job({ status: 'failed' })]} {...sortProps} {...handlers} onRetry={onRetry} />);
    expect(screen.queryAllByTitle('shares:cloudExport.revoke')).toHaveLength(0);
    fireEvent.click(screen.getAllByTitle('shares:cloudExport.retry')[0]);
    expect(onRetry).toHaveBeenCalledWith(1);
  });

  it('hides copy affordances when there is no share_link', () => {
    render(<CloudExportsTable jobs={[job({ share_link: null, status: 'pending' })]} {...sortProps} {...handlers} />);
    expect(screen.queryAllByTitle('shares:cloudExport.copyLink')).toHaveLength(0);
  });
});
