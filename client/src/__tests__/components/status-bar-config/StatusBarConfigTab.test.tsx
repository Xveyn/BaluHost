import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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
    { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x' },
    { pill_id: 'raid', name_key: 'statusBar.pills.raid.name', enabled: false, visibility: 'admin', visibility_locked: true, sort_order: 1, href: '/y' },
  ],
  show_bottom_upload: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
  (updateStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
});

function renderTab() {
  return render(<MemoryRouter><StatusBarConfigTab /></MemoryRouter>);
}

describe('StatusBarConfigTab', () => {
  it('lists all pills after load', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('pills.power.name')).toBeInTheDocument());
    expect(screen.getByText('pills.raid.name')).toBeInTheDocument();
  });

  it('save button calls updateStatusBarConfig', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('save')).toBeInTheDocument());
    await act(async () => { fireEvent.click(screen.getByText('save')); });
    expect(updateStatusBarConfig).toHaveBeenCalledTimes(1);
  });
});
