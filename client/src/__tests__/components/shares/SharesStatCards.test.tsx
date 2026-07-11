import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesStatCards } from '../../../components/shares/SharesStatCards';
import type { ShareStatistics } from '../../../api/shares';
import type { CloudExportStatistics } from '../../../api/cloud-export';

const stats: ShareStatistics = { active_file_shares: 3, total_file_shares: 5, files_shared_with_me: 2 };
const cloud: CloudExportStatistics = { active_exports: 1, total_exports: 4, failed_exports: 0, total_upload_bytes: 0 };

describe('SharesStatCards', () => {
  it('shows share stats on the shares tab', () => {
    render(<SharesStatCards activeTab="shares" statistics={stats} cloudStats={null} />);
    expect(screen.getByText('stats.userShares')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText('shares:cloudExport.activeShares')).toBeNull();
  });

  it('shows cloud stats on the cloud tab', () => {
    render(<SharesStatCards activeTab="cloud-exports" statistics={stats} cloudStats={cloud} />);
    expect(screen.getByText('shares:cloudExport.activeShares')).toBeInTheDocument();
    expect(screen.queryByText('stats.userShares')).toBeNull();
  });

  it('renders nothing without matching stats', () => {
    const { container } = render(<SharesStatCards activeTab="shares" statistics={null} cloudStats={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
