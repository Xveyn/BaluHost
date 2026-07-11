import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { SSDCacheEntryResponse } from '../../../../api/ssd-file-cache';
import { CacheEntriesTable } from '../../../../components/ssd-cache/file-cache/CacheEntriesTable';

const entry = (over: Partial<SSDCacheEntryResponse> = {}): SSDCacheEntryResponse => ({
  id: 1, array_name: 'md0', source_path: '/data/file.bin', file_size_bytes: 2048,
  access_count: 7, last_accessed: '2026-07-01T10:00:00Z', first_cached: '2026-06-01T10:00:00Z',
  is_valid: true, ...over,
});
const base = { entriesTotal: 1, page: 0, totalPages: 1, actionLoading: false,
  onEvict: () => {}, onPrevPage: () => {}, onNextPage: () => {} };

describe('CacheEntriesTable', () => {
  it('renders the empty-state row when there are no entries', () => {
    render(<CacheEntriesTable {...base} entries={[]} entriesTotal={0} />);
    expect(screen.getByText('No cached entries')).toBeInTheDocument();
  });
  it('renders a row per entry and fires onEvict with the entry id', () => {
    const onEvict = vi.fn();
    render(<CacheEntriesTable {...base} entries={[entry({ id: 42 })]} onEvict={onEvict} />);
    expect(screen.getByText('/data/file.bin')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Evict'));
    expect(onEvict).toHaveBeenCalledWith(42);
  });
  it('hides pagination when there is only one page', () => {
    render(<CacheEntriesTable {...base} entries={[entry()]} totalPages={1} />);
    expect(screen.queryByText(/Page 1 of/)).not.toBeInTheDocument();
  });
  it('disables prev on the first page and next on the last page, firing callbacks otherwise', () => {
    const onPrevPage = vi.fn(), onNextPage = vi.fn();
    // the Evict button has text; the two pagination controls are icon-only (empty textContent)
    const iconButtons = () => screen.getAllByRole('button').filter((b) => !b.textContent?.trim());
    const { rerender } = render(
      <CacheEntriesTable {...base} entries={[entry()]} page={0} totalPages={3}
        onPrevPage={onPrevPage} onNextPage={onNextPage} />,
    );
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    const [prev0, next0] = iconButtons(); // DOM order: ChevronLeft (prev), ChevronRight (next)
    expect(prev0).toBeDisabled();          // first page → prev disabled
    expect(next0).not.toBeDisabled();
    fireEvent.click(next0);
    expect(onNextPage).toHaveBeenCalledTimes(1);
    rerender(
      <CacheEntriesTable {...base} entries={[entry()]} page={2} totalPages={3}
        onPrevPage={onPrevPage} onNextPage={onNextPage} />,
    );
    expect(screen.getByText(/Page 3 of 3/)).toBeInTheDocument();
    const [prev2, next2] = iconButtons();
    expect(next2).toBeDisabled();           // last page → next disabled
    expect(prev2).not.toBeDisabled();
  });
});
