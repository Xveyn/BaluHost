/**
 * The generic dashboard plugin panel (#618).
 *
 * Two things this file pins down:
 *
 * - The live socket authenticates with a short-lived ws token. The backend
 *   rejects access tokens on /api/notifications/ws fail-closed, so the panel
 *   used to fail every handshake with 403 and never received a live update.
 * - REST polling keeps running while the socket is open. Panel updates are
 *   broadcast only by the primary Uvicorn worker, and the broadcast reaches
 *   only sockets in that process (#306) - a socket that lands on any of the
 *   other workers connects cleanly and then stays silent. Stopping the poll on
 *   onopen would freeze the panel there.
 *
 * Driven by helpers/fakeWebSocket.ts plus fake timers, like the notification
 * socket's tests.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen } from '@testing-library/react';

import { renderWithProviders } from '../../helpers/renderWithProviders';
import { FakeWebSocket, installFakeWebSocket } from '../../helpers/fakeWebSocket';
import { PluginDashboardPanel } from '../../../components/dashboard/PluginDashboardPanel';

const PANEL_ROUTE = '/api/dashboard/plugin-panel';
const WS_TOKEN_ROUTE = 'POST /api/notifications/ws-token';

const PANEL = {
  plugin_name: 'tapo_smart_plug',
  panel_type: 'stat',
  title: 'Leistung',
  icon: 'plug',
  accent: 'from-sky-500 to-blue-600',
  data: { value: '42 W', meta: 'NAS-Steckdose' },
};

async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function mount({ wsTokenFails = false } = {}) {
  const rendered = renderWithProviders(<PluginDashboardPanel />, {
    auth: { username: 'sven' },
    api: {
      [PANEL_ROUTE]: PANEL,
      [WS_TOKEN_ROUTE]: wsTokenFails
        ? { status: 500, body: { detail: 'no token for you' } }
        : { token: 'ws-abc' },
    },
  });
  await tick(100);
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

describe('socket authentication', () => {
  it('opens the socket with the scoped ws token, never the access token', async () => {
    await mount();

    expect(FakeWebSocket.instances).toHaveLength(1);
    const url = FakeWebSocket.last!.url;
    expect(url).toContain('/api/notifications/ws');
    expect(url).toContain('token=ws-abc');
    // renderWithProviders seeds the access token as "test-token"
    expect(url).not.toContain('test-token');
  });

  it('opens no socket while no plugin panel is active', async () => {
    // Each socket takes one of the per-user, per-worker connection slots
    // (MAX_CONNECTIONS_PER_USER) that the notification socket needs as well -
    // and with no panel every update would be dropped anyway.
    renderWithProviders(<PluginDashboardPanel />, {
      auth: { username: 'sven' },
      api: {
        [PANEL_ROUTE]: null,
        [WS_TOKEN_ROUTE]: { token: 'ws-abc' },
      },
    });
    await tick(100);

    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('opens no socket when the token exchange fails, and keeps polling', async () => {
    const { api } = await mount({ wsTokenFails: true });
    const before = api.callsTo(PANEL_ROUTE).length;

    await tick(10_000);

    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(api.callsTo(PANEL_ROUTE).length).toBeGreaterThan(before);
  });

  it('opens no socket when it unmounts before the ws token arrives', async () => {
    const { unmount } = renderWithProviders(<PluginDashboardPanel />, {
      auth: { username: 'sven' },
      api: {
        [PANEL_ROUTE]: PANEL,
        [WS_TOKEN_ROUTE]: { token: 'ws-abc' },
      },
    });
    unmount();
    await tick(100);

    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});

describe('updates', () => {
  it('keeps REST polling while the socket is open (#306)', async () => {
    const { api } = await mount();
    await act(async () => FakeWebSocket.last!.serverAccept());
    const before = api.callsTo(PANEL_ROUTE).length;

    await tick(10_000);

    expect(api.callsTo(PANEL_ROUTE).length).toBeGreaterThan(before);
  });

  it('applies a live update for the active plugin', async () => {
    await mount();
    await act(async () => FakeWebSocket.last!.serverAccept());
    // getByText, not findByText: its polling waits on real timers
    expect(screen.getByText('42 W')).toBeInTheDocument();

    await act(async () =>
      FakeWebSocket.last!.serverSend({
        type: 'dashboard_panel_update',
        payload: {
          panel_type: 'stat',
          plugin_name: 'tapo_smart_plug',
          data: { value: '57 W', meta: 'NAS-Steckdose' },
        },
      }),
    );

    expect(screen.getByText('57 W')).toBeInTheDocument();
  });

  it('closes the socket and stops polling on unmount', async () => {
    const { api, unmount } = await mount();
    const socket = FakeWebSocket.last!;
    await act(async () => socket.serverAccept());

    unmount();
    const after = api.callsTo(PANEL_ROUTE).length;
    await tick(30_000);

    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
    expect(api.callsTo(PANEL_ROUTE).length).toBe(after);
  });
});
