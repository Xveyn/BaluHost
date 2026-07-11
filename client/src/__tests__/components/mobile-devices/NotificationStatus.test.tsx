import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const getDeviceNotifications = vi.fn();
vi.mock('../../../api/mobile', () => ({
  getDeviceNotifications: (...a: unknown[]) => getDeviceNotifications(...a),
}));

import { NotificationStatus } from '../../../components/mobile-devices/NotificationStatus';

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe('NotificationStatus', () => {
  it('renders nothing when there are no notifications', async () => {
    getDeviceNotifications.mockResolvedValue([]);
    const { container } = render(<NotificationStatus deviceId="d1" />, { wrapper });
    // give the query a tick
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('renders the label and Fehlgeschlagen for a failed notification', async () => {
    getDeviceNotifications.mockResolvedValue([
      { notification_type: '7_days', sent_at: new Date().toISOString(), success: false },
    ]);
    render(<NotificationStatus deviceId="d1" />, { wrapper });
    expect(await screen.findByText('7 Tage Warnung')).toBeInTheDocument();
    expect(screen.getByText('Fehlgeschlagen')).toBeInTheDocument();
  });
});
