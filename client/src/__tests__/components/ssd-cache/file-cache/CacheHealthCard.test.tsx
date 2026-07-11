// CacheHealthCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CacheHealthResponse } from '../../../../api/ssd-file-cache';
import { CacheHealthCard } from '../../../../components/ssd-cache/file-cache/CacheHealthCard';

const health = (over: Partial<CacheHealthResponse> = {}): CacheHealthResponse => ({
  array_name: 'md0', is_mounted: true, ssd_total_bytes: 1024, ssd_available_bytes: 900,
  ssd_used_percent: 12.5, cache_dir_exists: true, ...over,
});

describe('CacheHealthCard', () => {
  it('shows Mounted when the ssd is mounted', () => {
    render(<CacheHealthCard health={health({ is_mounted: true })} />);
    expect(screen.getByText('Mounted')).toBeInTheDocument();
  });
  it('shows Not Mounted and Missing when unmounted with no cache dir', () => {
    render(<CacheHealthCard health={health({ is_mounted: false, cache_dir_exists: false })} />);
    expect(screen.getByText('Not Mounted')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();
  });
});
