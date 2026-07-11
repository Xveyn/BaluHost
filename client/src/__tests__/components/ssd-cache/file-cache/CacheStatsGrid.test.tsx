// CacheStatsGrid.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SSDCacheStats } from '../../../../api/ssd-file-cache';
import { CacheStatsGrid } from '../../../../components/ssd-cache/file-cache/CacheStatsGrid';

const stats = (over: Partial<SSDCacheStats> = {}): SSDCacheStats => ({
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, usage_percent: 50, total_entries: 3, valid_entries: 2,
  total_hits: 10, total_misses: 5, hit_rate_percent: 66.7, total_bytes_served: 2048,
  ssd_available_bytes: 900, ssd_total_bytes: 1024, ...over,
});

describe('CacheStatsGrid', () => {
  it('shows Enabled status when enabled', () => {
    render(<CacheStatsGrid stats={stats({ is_enabled: true })} />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });
  it('shows Disabled status when disabled', () => {
    render(<CacheStatsGrid stats={stats({ is_enabled: false })} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });
  it('renders the hit-rate percentage', () => {
    render(<CacheStatsGrid stats={stats({ hit_rate_percent: 66.7 })} />);
    expect(screen.getByText('66.7%')).toBeInTheDocument();
  });
});
