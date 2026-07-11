import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { CloudStatusBadge } from '../../../components/shares/CloudStatusBadge';
import type { CloudExportJob } from '../../../api/cloud-export';

// Full object (no partial `as` cast): all required fields present, then override.
const job = (over: Partial<CloudExportJob> = {}): CloudExportJob => ({
  id: 1, user_id: 1, connection_id: 1, source_path: '/f', file_name: 'f',
  is_directory: false, file_size_bytes: 100, cloud_folder: '/', cloud_path: null,
  share_link: null, link_type: 'view', status: 'pending', progress_bytes: 0,
  error_message: null, created_at: '2026-01-01T00:00:00Z', completed_at: null,
  expires_at: null, ...over,
});

describe('CloudStatusBadge', () => {
  it('renders the ready status key', () => {
    render(<CloudStatusBadge job={job({ status: 'ready' })} />);
    expect(screen.getByText('shares:cloudExport.statusReady')).toBeInTheDocument();
  });

  it('shows upload percent when uploading with a known size', () => {
    render(<CloudStatusBadge job={job({ status: 'uploading', progress_bytes: 50, file_size_bytes: 100 })} />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('falls back to the generic status text for unknown status', () => {
    // status is a closed union; force an out-of-union value to hit the default arm.
    render(<CloudStatusBadge job={{ ...job(), status: 'weird' as unknown as CloudExportJob['status'] }} />);
    expect(screen.getByText('weird')).toBeInTheDocument();
  });
});
