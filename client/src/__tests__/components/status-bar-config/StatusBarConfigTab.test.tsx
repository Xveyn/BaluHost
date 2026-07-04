import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../helpers/queryClient';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/statusBar', () => ({
  getStatusBarConfig: vi.fn(),
  updateStatusBarConfig: vi.fn(),
  getStatusBarState: vi.fn().mockResolvedValue({ pills: [], show_bottom_upload: true }),
}));

import { getStatusBarConfig, updateStatusBarConfig } from '../../../api/statusBar';
import { StatusBarConfigTab } from '../../../components/status-bar-config/StatusBarConfigTab';

const cfg = {
  pills: [
    { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x', icon: 'Zap', display_mode: 'always', display_mode_configurable: false },
    { pill_id: 'raid', name_key: 'statusBar.pills.raid.name', enabled: false, visibility: 'admin', visibility_locked: true, sort_order: 1, href: '/y', icon: 'HardDrive', display_mode: 'always', display_mode_configurable: false },
  ],
  show_bottom_upload: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
  (updateStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
});

function renderTab() {
  // TopbarStatusStrip (live preview) uses useStatusBarState → useQuery, so a
  // QueryClient must be in scope even though the getStatusBarState call is mocked.
  const client = createTestQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><StatusBarConfigTab /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StatusBarConfigTab', () => {
  it('lists all pills after load', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('pills.power.name')).toBeInTheDocument());
    expect(screen.getByText('pills.raid.name')).toBeInTheDocument();
  });

  it('renders the pill icon in the live preview', async () => {
    (getStatusBarConfig as any).mockResolvedValue({
      pills: [
        { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: true, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x', icon: 'Zap', display_mode: 'always', display_mode_configurable: false },
      ],
      show_bottom_upload: true,
    });
    const { container } = renderTab();
    await waitFor(() => expect(screen.getByText('save')).toBeInTheDocument());
    // The enabled pill's lucide icon (Zap) must appear in the Live Preview.
    expect(container.querySelector('.lucide-zap')).toBeInTheDocument();
  });

  it('save button calls updateStatusBarConfig', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('save')).toBeInTheDocument());
    await act(async () => { fireEvent.click(screen.getByText('save')); });
    expect(updateStatusBarConfig).toHaveBeenCalledTimes(1);
  });
});
