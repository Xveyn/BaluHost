import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharedWithMeTable } from '../../../components/shares/SharedWithMeTable';
import type { SharedWithMe } from '../../../api/shares';

// Full object (all required SharedWithMe fields), then override.
const item = (over: Partial<SharedWithMe> = {}): SharedWithMe => ({
  share_id: 7, file_id: 10, file_name: 'photo.jpg', file_path: '/photo.jpg',
  file_size: 0, is_directory: false, owner_username: 'carol', owner_id: 3,
  can_read: true, can_write: false, can_delete: false, can_share: false,
  shared_at: '2026-01-01T00:00:00Z', expires_at: null, is_expired: false, ...over,
});

const sortProps = { sortKey: null, sortDirection: null, onSort: vi.fn() };

describe('SharedWithMeTable', () => {
  it('shows the empty state when nothing is shared', () => {
    render(<SharedWithMeTable items={[]} allCount={0} {...sortProps} />);
    expect(screen.getByText('empty.noFilesShared')).toBeInTheDocument();
  });

  it('renders the owner and file name for an item', () => {
    render(<SharedWithMeTable items={[item()]} allCount={1} {...sortProps} />);
    expect(screen.getAllByText('photo.jpg').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/carol/).length).toBeGreaterThan(0);
  });
});
