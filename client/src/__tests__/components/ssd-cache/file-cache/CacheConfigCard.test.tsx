import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { SSDCacheConfigUpdate, SSDCacheConfigResponse } from '../../../../api/ssd-file-cache';
import { CacheConfigCard } from '../../../../components/ssd-cache/file-cache/CacheConfigCard';

const config: SSDCacheConfigResponse = {
  array_name: 'md0', is_enabled: true, cache_path: '/ssd', max_size_bytes: 1024,
  current_size_bytes: 512, eviction_policy: 'lfru', min_file_size_bytes: 1,
  max_file_size_bytes: 100, sequential_cutoff_bytes: 50, total_hits: 0,
  total_misses: 0, total_bytes_served_from_cache: 0, updated_at: null,
};
const form: SSDCacheConfigUpdate = {
  is_enabled: true, max_size_bytes: 1024, eviction_policy: 'lfru',
  min_file_size_bytes: 1, max_file_size_bytes: 100, sequential_cutoff_bytes: 50,
};
const base = {
  configForm: form, config, actionLoading: false,
  onConfigChange: () => {}, onSave: () => {}, onReset: () => {},
};

describe('CacheConfigCard', () => {
  it('disables Save when not dirty and enables it when dirty', () => {
    const { rerender } = render(<CacheConfigCard {...base} configDirty={false} />);
    expect(screen.getByText('Save Configuration').closest('button')).toBeDisabled();
    rerender(<CacheConfigCard {...base} configDirty={true} />);
    expect(screen.getByText('Save Configuration').closest('button')).not.toBeDisabled();
  });
  it('shows the Reset button only when dirty', () => {
    const { rerender } = render(<CacheConfigCard {...base} configDirty={false} />);
    expect(screen.queryByText('Reset')).not.toBeInTheDocument();
    rerender(<CacheConfigCard {...base} configDirty={true} />);
    expect(screen.getByText('Reset')).toBeInTheDocument();
  });
  it('fires onConfigChange when the enabled checkbox toggles', () => {
    const onConfigChange = vi.fn();
    render(<CacheConfigCard {...base} configDirty={false} onConfigChange={onConfigChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onConfigChange).toHaveBeenCalledWith('is_enabled', false);
  });
  it('fires onSave when Save is clicked (dirty)', () => {
    const onSave = vi.fn();
    render(<CacheConfigCard {...base} configDirty={true} onSave={onSave} />);
    fireEvent.click(screen.getByText('Save Configuration'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});
