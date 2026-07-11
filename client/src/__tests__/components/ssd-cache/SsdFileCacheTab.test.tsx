import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SSDCacheStats, SSDCacheConfigResponse } from '../../../api/ssd-file-cache';
import type { UseSsdFileCacheResult } from '../../../hooks/useSsdFileCache';

const stats: SSDCacheStats = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, usage_percent: 50, total_entries: 1, valid_entries: 1,
  total_hits: 5, total_misses: 1, hit_rate_percent: 83.3, total_bytes_served: 100,
  ssd_available_bytes: 900, ssd_total_bytes: 1024,
};
const config: SSDCacheConfigResponse = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, eviction_policy: 'lfru', min_file_size_bytes: 1,
  max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 5,
  total_misses: 1, total_bytes_served_from_cache: 100, updated_at: null,
};

const hookValue: UseSsdFileCacheResult = {
  tabView: 'cache', setTabView: vi.fn(), arrays: ['md0'], selectedArray: 'md0',
  setSelectedArray: vi.fn(), stats, config, health: null, entries: [], entriesTotal: 0,
  loading: false, error: null, actionLoading: false, configForm: {}, configDirty: false,
  page: 0, setPage: vi.fn(), pageSize: 20, handleConfigChange: vi.fn(),
  handleSaveConfig: vi.fn(), resetConfigForm: vi.fn(), handleEvictEntry: vi.fn(),
  handleTriggerEviction: vi.fn(), handleClearCache: vi.fn(), loadData: vi.fn(),
  loadEntries: vi.fn(), dialog: null,
};
vi.mock('../../../hooks/useSsdFileCache', () => ({ useSsdFileCache: () => hookValue }));
vi.mock('../../../components/ssd-cache/MigrationPanel', () => ({ default: () => <div data-testid="migration" /> }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb: string) => fb }) }));

import SsdFileCacheTab from '../../../components/ssd-cache/SsdFileCacheTab';

describe('SsdFileCacheTab', () => {
  beforeEach(() => {
    Object.assign(hookValue, { tabView: 'cache', arrays: ['md0'], stats, config, loading: false });
  });

  it('renders the cache view (stats + config + actions) for a populated fixture', () => {
    render(<SsdFileCacheTab />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();      // stats grid
    expect(screen.getByText('Configuration')).toBeInTheDocument(); // config card
    expect(screen.getByRole('heading', { name: 'Actions' })).toBeInTheDocument(); // actions card (getByText collides with the entries table's "Actions" column header)
    expect(screen.queryByTestId('migration')).not.toBeInTheDocument();
  });

  it('renders MigrationPanel when tabView is migration', () => {
    hookValue.tabView = 'migration';
    render(<SsdFileCacheTab />);
    expect(screen.getByTestId('migration')).toBeInTheDocument();
    expect(screen.queryByText('Configuration')).not.toBeInTheDocument();
  });

  it('shows the no-arrays message when there are no arrays', () => {
    Object.assign(hookValue, { arrays: [], loading: false, stats: null });
    render(<SsdFileCacheTab />);
    expect(screen.getByText(/No RAID arrays found/)).toBeInTheDocument();
  });
});
