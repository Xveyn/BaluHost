// client/src/__tests__/components/shares/SharesToolbar.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesToolbar } from '../../../components/shares/SharesToolbar';

const base = {
  searchQuery: '',
  onSearch: vi.fn(),
  statusFilter: 'all' as const,
  onStatusFilter: vi.fn(),
  showFilters: false,
  onToggleFilters: vi.fn(),
  showCreateButton: true,
  onCreate: vi.fn(),
};

describe('SharesToolbar', () => {
  it('reports search input changes', () => {
    const onSearch = vi.fn();
    render(<SharesToolbar {...base} onSearch={onSearch} />);
    fireEvent.change(screen.getByPlaceholderText('search.placeholder'), { target: { value: 'abc' } });
    expect(onSearch).toHaveBeenCalledWith('abc');
  });

  it('hides the create button when showCreateButton=false', () => {
    render(<SharesToolbar {...base} showCreateButton={false} />);
    expect(screen.queryByText('buttons.shareWithUser')).toBeNull();
  });

  it('renders the status radios only when showFilters=true', () => {
    const { rerender } = render(<SharesToolbar {...base} showFilters={false} />);
    expect(screen.queryByText('search.active')).toBeNull();
    rerender(<SharesToolbar {...base} showFilters={true} />);
    expect(screen.getByText('search.active')).toBeInTheDocument();
  });
});
