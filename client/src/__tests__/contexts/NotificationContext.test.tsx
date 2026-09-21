/**
 * NotificationContext — the refetch debounce on `notification_state` fan-out.
 *
 * Task 6 wires useNotificationSocket's `notification_state` frame to a
 * debounced refetch (NotificationContext.tsx): a state change made elsewhere
 * (another tab, another device) is fanned out to every connection of the
 * user, including the one that caused it — so 15 clicks on this very tab
 * come back as 15 frames on its own socket. Without the debounce, each frame
 * would trigger its own GET /api/notifications, hammering the 30/min limit.
 * That guarantee was so far only checked by reading the source; this file
 * exercises it against the real timer and the real route table, the way
 * useNotificationSocket.test.tsx exercises the socket itself.
 *
 * Separate file from the hook's test: this one mounts the Provider (and,
 * through it, the hook) rather than the hook in isolation, with a consumer of
 * `useNotifications()` instead of `useNotificationSocket()` directly — same
 * split the codebase already uses for hooks vs. contexts
 * (`__tests__/hooks/` vs. `__tests__/contexts/`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act } from '@testing-library/react';

import { renderWithProviders } from '../helpers/renderWithProviders';
import { FakeWebSocket, installFakeWebSocket } from '../helpers/fakeWebSocket';
import { NotificationProvider, useNotifications } from '../../contexts/NotificationContext';

const WS_TOKEN_ROUTE = 'POST /api/notifications/ws-token';
const LIST_ROUTE = 'GET /api/notifications';
const UNREAD_ROUTE = 'GET /api/notifications/unread-count';

function Consumer() {
  const { unreadCount } = useNotifications();
  return <p data-testid="unread">{unreadCount}</p>;
}

/** Render, sign in, and let the initial fetch + the socket's 50ms connect delay settle. */
async function mount() {
  const rendered = renderWithProviders(
    <NotificationProvider>
      <Consumer />
    </NotificationProvider>,
    {
      auth: { username: 'sven' },
      api: {
        [WS_TOKEN_ROUTE]: { token: 'ws-abc' },
        [LIST_ROUTE]: { notifications: [], total: 0, unread_count: 0, page: 1, page_size: 20 },
        [UNREAD_ROUTE]: { count: 0, by_category: null },
      },
    },
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
  return rendered;
}

beforeEach(() => {
  vi.useFakeTimers();
  installFakeWebSocket();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('refetch debounce on notification_state', () => {
  it('faltet mehrere Frames innerhalb der Entprellung zu genau einem Nachladevorgang zusammen', async () => {
    const rendered = await mount();
    await act(async () => {
      FakeWebSocket.last!.serverAccept();
    });

    const before = rendered.api.callsTo('/api/notifications', 'GET').length;

    // Drei Zustandswechsel praktisch gleichzeitig -- wie 15 Klicks, nur kuerzer.
    await act(async () => {
      FakeWebSocket.last!.serverSend({
        type: 'notification_state',
        payload: { ids: [1], action: 'read' },
      });
    });
    await act(async () => {
      FakeWebSocket.last!.serverSend({
        type: 'notification_state',
        payload: { ids: [2], action: 'read' },
      });
    });
    await act(async () => {
      FakeWebSocket.last!.serverSend({
        type: 'notification_state',
        payload: { ids: [3], action: 'read' },
      });
    });

    // Noch innerhalb der 400ms seit dem letzten Frame: kein Nachladen.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(rendered.api.callsTo('/api/notifications', 'GET').length).toBe(before);

    // Entprellung abgelaufen: genau EIN Nachladevorgang fuer alle drei Frames.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(rendered.api.callsTo('/api/notifications', 'GET').length).toBe(before + 1);
  });

  it('raeumt den Timer beim Unmount auf -- kein Nachladen danach, keine React-Warnung', async () => {
    const rendered = await mount();
    await act(async () => {
      FakeWebSocket.last!.serverAccept();
    });

    const before = rendered.api.callsTo('/api/notifications', 'GET').length;

    await act(async () => {
      FakeWebSocket.last!.serverSend({
        type: 'notification_state',
        payload: { ids: [1], action: 'read' },
      });
    });

    // Ab hier zaehlt jeder console.error: der wartende Timer darf beim Abbau
    // weder feuern noch einen State-Update-Warnhinweis auf eine bereits
    // abgebaute Komponente ausloesen.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Unmount, bevor die 400ms Entprellung um sind.
    await act(async () => {
      rendered.unmount();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(rendered.api.callsTo('/api/notifications', 'GET').length).toBe(before);
    expect(consoleError).not.toHaveBeenCalled();

    consoleError.mockRestore();
  });
});
