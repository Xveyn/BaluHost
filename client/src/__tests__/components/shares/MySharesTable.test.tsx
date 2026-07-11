// client/src/__tests__/components/shares/MySharesTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { MySharesTable } from '../../../components/shares/MySharesTable';
import type { FileShare } from '../../../api/shares';

// Full object (all required FileShare fields), then override.
const share = (over: Partial<FileShare> = {}): FileShare => ({
  id: 1, file_id: 10, owner_id: 1, shared_with_user_id: 2,
  can_read: true, can_write: false, can_delete: false, can_share: false,
  expires_at: null, created_at: '2026-01-01T00:00:00Z', last_accessed_at: null,
  is_expired: false, is_accessible: true,
  owner_username: 'alice', shared_with_username: 'bob',
  file_name: 'report.pdf', file_path: '/report.pdf', file_size: 0, is_directory: false,
  ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };

describe('MySharesTable', () => {
  it('shows the "no shares" empty state when there are none at all', () => {
    render(<MySharesTable shares={[]} allCount={0} onEdit={vi.fn()} onDelete={vi.fn()} {...sortProps} />);
    expect(screen.getByText('empty.noShares')).toBeInTheDocument();
  });

  it('shows the "no matching" empty state when filtered to zero', () => {
    render(<MySharesTable shares={[]} allCount={3} onEdit={vi.fn()} onDelete={vi.fn()} {...sortProps} />);
    expect(screen.getByText('empty.noMatchingShares')).toBeInTheDocument();
  });

  it('fires onEdit and onDelete from the row actions (desktop)', () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<MySharesTable shares={[share()]} allCount={1} onEdit={onEdit} onDelete={onDelete} {...sortProps} />);
    // file name appears in both desktop + mobile views
    expect(screen.getAllByText('report.pdf').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByTitle('buttons.edit')[0]);
    fireEvent.click(screen.getAllByTitle('buttons.revoke')[0]);
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
    expect(onDelete).toHaveBeenCalledWith(1);
  });
});
