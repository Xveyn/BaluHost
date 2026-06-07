import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import NfsManagementCard from '../../../components/nfs/NfsManagementCard';
import type { NfsExport, NfsStatus } from '../../../api/nfs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../api/nfs', () => ({
  getNfsStatus: vi.fn(),
  listNfsExports: vi.fn(),
  createNfsExport: vi.fn(),
  updateNfsExport: vi.fn(),
  deleteNfsExport: vi.fn(),
}));

import { getNfsStatus, listNfsExports } from '../../../api/nfs';

const status: NfsStatus = { is_running: true, version: null, exports_count: 1 };
const exports: NfsExport[] = [
  {
    id: 1, path: 'Media', clients: '192.168.1.0/24', read_only: false,
    root_squash: true, enabled: true, comment: null,
    mount_target: '192.168.1.10:/srv/baluhost/Media',
  },
];

describe('NfsManagementCard', () => {
  beforeEach(() => {
    vi.mocked(getNfsStatus).mockResolvedValue(status);
    vi.mocked(listNfsExports).mockResolvedValue(exports);
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders the export list from the API', async () => {
    render(<NfsManagementCard />);
    await waitFor(() => expect(screen.getByText('Media')).toBeInTheDocument());
    expect(screen.getByText('192.168.1.0/24')).toBeInTheDocument();
    expect(getNfsStatus).toHaveBeenCalled();
    expect(listNfsExports).toHaveBeenCalled();
  });
});
