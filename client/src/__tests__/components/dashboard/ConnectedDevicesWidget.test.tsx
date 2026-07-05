import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../helpers/queryClient';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { count?: number }) => (o?.count != null ? `${k}:${o.count}` : k) }),
}));
vi.mock('../../../api/devices', () => ({ getAllDevices: vi.fn() }));

import { getAllDevices } from '../../../api/devices';
import { ConnectedDevicesWidget } from '../../../components/dashboard/ConnectedDevicesWidget';

beforeEach(() => vi.clearAllMocks());

function renderWidget() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter><ConnectedDevicesWidget /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConnectedDevicesWidget (query migration #299)', () => {
  it('treats a 403 as "no devices" instead of surfacing an error', async () => {
    (getAllDevices as any).mockRejectedValue(new Error('Request failed with status code 403'));
    renderWidget();
    // Empty state (clickable), NOT the "unable to load" error state.
    await waitFor(() =>
      expect(screen.getByText('dashboard:devices.noDevicesRegistered')).toBeInTheDocument(),
    );
    expect(screen.queryByText('dashboard:devices.unableToLoad')).not.toBeInTheDocument();
  });

  it('renders mobile/desktop counts on success', async () => {
    (getAllDevices as any).mockResolvedValue([
      { id: 1, name: 'Phone', type: 'mobile', is_active: true, last_seen: null },
      { id: 2, name: 'Laptop', type: 'desktop', is_active: true, last_seen: null },
      { id: 3, name: 'Tablet', type: 'mobile', is_active: true, last_seen: null },
    ]);
    renderWidget();
    await waitFor(() => expect(screen.getByText('dashboard:devices.mobile')).toBeInTheDocument());
    // 2 mobile, 1 desktop
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows the error state for a non-403 failure', async () => {
    (getAllDevices as any).mockRejectedValue(new Error('Request failed with status code 500'));
    renderWidget();
    await waitFor(() =>
      expect(screen.getByText('dashboard:devices.unableToLoad')).toBeInTheDocument(),
    );
  });
});
