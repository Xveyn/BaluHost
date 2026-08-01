/**
 * The notification socket — the last of T3/#317's five risk areas.
 *
 * Its whole substance is failure handling: reconnect with a growing delay, a
 * ceiling on attempts, an intentional close that must NOT reconnect, and a
 * ws-token exchange that can fail before a socket even exists. None of that is
 * reachable through the UI, and all of it is one `if` away from either a
 * reconnect storm or a silently dead notification bell.
 *
 * Driven by helpers/fakeWebSocket.ts plus fake timers; the ws-token request
 * goes through the normal route table (it is an ordinary axios POST).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen } from '@testing-library/react';
import { useEffect } from 'react';

import { renderWithProviders } from '../helpers/renderWithProviders';
import { FakeWebSocket, installFakeWebSocket } from '../helpers/fakeWebSocket';
import { useAuth } from '../../contexts/AuthContext';
import useNotificationSocket, {
  type UseNotificationSocketOptions,
} from '../../hooks/useNotificationSocket';

const WS_TOKEN_ROUTE = 'POST /api/notifications/ws-token';

/**
 * Handle onto the hook's own API so a test can call disconnect()/markRead().
 * Filled in an EFFECT, not during render: assigning to an outer variable while
 * rendering is a side effect the react-compiler lint rule rejects, and it
 * would also be wrong under a re-render that React discards.
 */
const socket: { current: ReturnType<typeof useNotificationSocket> | null } = { current: null };

function Harness(props: UseNotificationSocketOptions) {
  const hookApi = useNotificationSocket(props);
  useEffect(() => {
    socket.current = hookApi;
  });
  const { token } = useAuth();
  return (
    <div>
      <p data-testid="auth">{token ? 'angemeldet' : 'lädt'}</p>
      <p data-testid="connected">{hookApi.connected ? 'verbunden' : 'getrennt'}</p>
      <p data-testid="unread">{hookApi.unreadCount}</p>
      <p data-testid="latest">{hookApi.latestNotification?.title ?? '—'}</p>
      <p data-testid="error">{hookApi.error ?? '—'}</p>
    </div>
  );
}

/** Render, sign in, and let the hook's 50ms connect delay elapse. */
async function mount(
  props: UseNotificationSocketOptions = {},
  { signedIn = true, wsTokenFails = false } = {},
) {
  const rendered = renderWithProviders(<Harness {...props} />, {
    auth: signedIn ? { username: 'sven' } : false,
    api: {
      [WS_TOKEN_ROUTE]: wsTokenFails
        ? { status: 500, body: { detail: 'no token for you' } }
        : { token: 'ws-abc' },
    },
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
  return rendered;
}

/** Let pending promises settle and timers up to `ms` fire. */
async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  installFakeWebSocket();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('connecting', () => {
  it('opens exactly one socket, with the short-lived ws token in the URL', async () => {
    await mount();

    expect(FakeWebSocket.instances).toHaveLength(1);
    // The scoped token, not the access token — it ends up in proxy logs via
    // the query string, which is why the hook exchanges one in the first place.
    expect(FakeWebSocket.last!.url).toContain('token=ws-abc');
    expect(FakeWebSocket.last!.url).toContain('/api/notifications/ws');
  });

  it('stays quiet without a signed-in user', async () => {
    await mount({}, { signedIn: false });

    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('stays quiet when disabled', async () => {
    await mount({ enabled: false });

    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('reports connected once the handshake completes', async () => {
    await mount();
    expect(screen.getByTestId('connected')).toHaveTextContent('getrennt');

    await act(async () => FakeWebSocket.last!.serverAccept());

    expect(screen.getByTestId('connected')).toHaveTextContent('verbunden');
  });

  it('pings every 30s while open', async () => {
    await mount();
    await act(async () => FakeWebSocket.last!.serverAccept());

    await tick(30_000);
    expect(FakeWebSocket.last!.sentMessages()).toEqual([{ type: 'ping' }]);

    await tick(30_000);
    expect(FakeWebSocket.last!.sentMessages()).toHaveLength(2);
  });
});

describe('incoming frames', () => {
  it('surfaces a notification and calls back', async () => {
    const onNotification = vi.fn();
    await mount({ onNotification });
    await act(async () => FakeWebSocket.last!.serverAccept());

    await act(async () =>
      FakeWebSocket.last!.serverSend({
        type: 'notification',
        payload: { id: 7, title: 'RAID degraded' },
      }),
    );

    expect(screen.getByTestId('latest')).toHaveTextContent('RAID degraded');
    expect(onNotification).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it('surfaces the unread count and calls back', async () => {
    const onUnreadCountChange = vi.fn();
    await mount({ onUnreadCountChange });
    await act(async () => FakeWebSocket.last!.serverAccept());

    await act(async () =>
      FakeWebSocket.last!.serverSend({ type: 'unread_count', payload: { count: 12 } }),
    );

    expect(screen.getByTestId('unread')).toHaveTextContent('12');
    expect(onUnreadCountChange).toHaveBeenCalledWith(12);
  });

  it('shrugs off pongs and garbage instead of crashing the bell', async () => {
    await mount();
    await act(async () => FakeWebSocket.last!.serverAccept());
    await act(async () =>
      FakeWebSocket.last!.serverSend({ type: 'unread_count', payload: { count: 3 } }),
    );

    await act(async () => FakeWebSocket.last!.serverSend({ type: 'pong' }));
    await act(async () => FakeWebSocket.last!.serverSendRaw('<html>not json</html>'));
    await act(async () => FakeWebSocket.last!.serverSend({ type: 'something_new' }));

    expect(screen.getByTestId('unread')).toHaveTextContent('3');
    expect(screen.getByTestId('connected')).toHaveTextContent('verbunden');
  });
});

describe('reconnecting', () => {
  it('waits longer after each drop', async () => {
    await mount({ reconnectDelay: 1000 });
    await act(async () => FakeWebSocket.last!.serverAccept());

    await act(async () => FakeWebSocket.last!.serverDrop());
    await tick(999);
    expect(FakeWebSocket.instances).toHaveLength(1); // not yet
    await tick(1);
    expect(FakeWebSocket.instances).toHaveLength(2); // 1 x delay

    await act(async () => FakeWebSocket.last!.serverDrop());
    await tick(1000);
    expect(FakeWebSocket.instances).toHaveLength(2); // 2 x delay, not there yet
    await tick(1000);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it('gives up after the configured number of attempts', async () => {
    await mount({ reconnectDelay: 100, maxReconnectAttempts: 2 });

    for (let attempt = 0; attempt < 3; attempt++) {
      await act(async () => FakeWebSocket.last!.serverDrop());
      await tick(1000);
    }

    // one initial + two retries, then it stops trying
    expect(FakeWebSocket.instances).toHaveLength(3);
    expect(screen.getByTestId('error')).toHaveTextContent('Max reconnection attempts reached');
  });

  it('starts counting from zero again after a successful handshake', async () => {
    await mount({ reconnectDelay: 100, maxReconnectAttempts: 2 });

    await act(async () => FakeWebSocket.last!.serverDrop());
    await tick(200);
    await act(async () => FakeWebSocket.last!.serverAccept()); // recovered

    // The budget must be full again, otherwise a box that drops once an hour
    // would eventually stop reconnecting for good.
    await act(async () => FakeWebSocket.last!.serverDrop());
    await tick(200);
    await act(async () => FakeWebSocket.last!.serverDrop());
    await tick(400);

    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(4);
    expect(screen.getByTestId('error')).toHaveTextContent('—');
  });

  it('does NOT reconnect after an intentional close', async () => {
    await mount({ reconnectDelay: 100 });
    await act(async () => FakeWebSocket.last!.serverAccept());

    await act(async () => socket.current!.disconnect());
    await tick(5000);

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.last!.closedWith).toEqual({ code: 1000, reason: 'Client disconnect' });
    expect(screen.getByTestId('connected')).toHaveTextContent('getrennt');
  });

  it('retries when the ws-token exchange fails, without opening a socket', async () => {
    // The token exchange happens BEFORE any socket exists, so there is no
    // onclose to drive the retry — the hook has to schedule it itself.
    await mount({ reconnectDelay: 100 }, { wsTokenFails: true });

    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(screen.getByTestId('error')).toHaveTextContent('Connection failed');

    await tick(200);
    expect(screen.getByTestId('error')).toHaveTextContent('Connection failed');
  });
});

describe('sending', () => {
  it('marks a notification read over the open socket', async () => {
    await mount();
    await act(async () => FakeWebSocket.last!.serverAccept());

    await act(async () => socket.current!.markRead(42));

    expect(FakeWebSocket.last!.sentMessages()).toEqual([
      { type: 'mark_read', payload: { notification_id: 42 } },
    ]);
  });

  it('drops a mark-read while the socket is not open instead of throwing', async () => {
    await mount();

    await act(async () => socket.current!.markRead(42));

    expect(FakeWebSocket.last!.sent).toHaveLength(0);
  });
});
