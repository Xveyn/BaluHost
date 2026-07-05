import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../helpers/queryClient';
import { queryKeys } from '../../../lib/queryKeys';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/pihole', () => ({
  getCollectorStatus: vi.fn(),
  updateCollectorConfig: vi.fn(),
}));

import { getCollectorStatus, updateCollectorConfig } from '../../../api/pihole';
import type { QueryCollectorStatus as CollectorStatus } from '../../../api/pihole';
import QueryCollectorStatus from '../../../components/pihole/QueryCollectorStatus';

function collector(over: Partial<CollectorStatus> = {}): CollectorStatus {
  return {
    running: true,
    is_enabled: true,
    last_poll_at: null,
    total_queries_stored: 100,
    last_error: null,
    last_error_at: null,
    poll_interval_seconds: 30,
    retention_days: 30,
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

function renderCollector() {
  const client = createTestQueryClient();
  render(
    <QueryClientProvider client={client}>
      <QueryCollectorStatus />
    </QueryClientProvider>,
  );
  return client;
}

describe('QueryCollectorStatus (query migration #299)', () => {
  it('seeds the form once and a later poll does NOT clobber it (dirty-guard)', async () => {
    (getCollectorStatus as any).mockResolvedValue(collector({ poll_interval_seconds: 30 }));
    const client = renderCollector();

    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument());
    const pollInput = screen.getAllByRole('spinbutton')[0] as HTMLInputElement;
    expect(pollInput.value).toBe('30');

    // Next poll returns a DIFFERENT server config + new total.
    (getCollectorStatus as any).mockResolvedValue(
      collector({ poll_interval_seconds: 99, total_queries_stored: 200 }),
    );
    await act(async () => {
      await client.invalidateQueries({ queryKey: queryKeys.pihole.collectorStatus() });
    });

    // The status display refreshed (200), but the form field stays at the seeded 30.
    await waitFor(() => expect(screen.getByText('200')).toBeInTheDocument());
    expect((screen.getAllByRole('spinbutton')[0] as HTMLInputElement).value).toBe('30');
  });

  it('save sends the edited config values', async () => {
    (getCollectorStatus as any).mockResolvedValue(collector());
    (updateCollectorConfig as any).mockResolvedValue(collector({ poll_interval_seconds: 45 }));
    renderCollector();

    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument());
    const pollInput = screen.getAllByRole('spinbutton')[0] as HTMLInputElement;
    fireEvent.change(pollInput, { target: { value: '45' } });

    fireEvent.click(screen.getByText('collector.save'));

    await waitFor(() =>
      expect(updateCollectorConfig).toHaveBeenCalledWith({
        poll_interval_seconds: 45,
        retention_days: 30,
      }),
    );
  });
});
