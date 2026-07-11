import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { VCLStorageInfo } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb?: string) => fb ?? _k }) }));
import { VclStorageInfoCard } from '../../../../components/vcl/vcl-settings/VclStorageInfoCard';

const info = (over: Partial<VCLStorageInfo> = {}): VCLStorageInfo => ({
  storage_path: '/mnt/vcl', is_custom_path: false, blob_count: 42,
  total_compressed_bytes: 1000, disk_total_bytes: 2000, disk_available_bytes: 1500,
  disk_used_percent: 25, ...over,
});

describe('VclStorageInfoCard', () => {
  it('renders the storage path', () => {
    render(<VclStorageInfoCard storageInfo={info()} />);
    expect(screen.getByText('/mnt/vcl')).toBeInTheDocument();
  });
  it('shows the Custom Path badge only when is_custom_path', () => {
    const { rerender } = render(<VclStorageInfoCard storageInfo={info({ is_custom_path: false })} />);
    expect(screen.queryByText('Custom Path')).not.toBeInTheDocument();
    rerender(<VclStorageInfoCard storageInfo={info({ is_custom_path: true })} />);
    expect(screen.getByText('Custom Path')).toBeInTheDocument();
  });
});
