/**
 * A hand-written WebSocket stand-in for tests.
 *
 * jsdom ships no WebSocket, and the alternatives (a request-mock framework's
 * ws support, a real local server) both bring more machinery than the thing
 * being tested. What a socket test actually needs is control over the four
 * events and a record of what was sent — that is this file.
 *
 * The class mirrors the parts of the real API the app touches: the readyState
 * constants (`useNotificationSocket` compares against WebSocket.OPEN), the
 * instance readyState, send() and close(). Everything prefixed `server*` is a
 * test lever, not part of the browser API.
 */
import { vi } from 'vitest';

export interface FakeCloseEvent {
  code: number;
  reason?: string;
}

export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  /** Every socket the code under test opened, oldest first. */
  static instances: FakeWebSocket[] = [];

  static get last(): FakeWebSocket | undefined {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }

  static reset(): void {
    FakeWebSocket.instances = [];
  }

  readonly url: string;
  readyState: number = FakeWebSocket.CONNECTING;
  /** Raw frames the app sent, in order. */
  readonly sent: string[] = [];
  /** Arguments of the app's close() call, if it closed the socket itself. */
  closedWith: FakeCloseEvent | null = null;

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: ((event: FakeCloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000, reason = ''): void {
    this.closedWith = { code, reason };
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason });
  }

  // ---- test levers -------------------------------------------------------

  /** The handshake completed. */
  serverAccept(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  /** Deliver a JSON frame the way the backend would. */
  serverSend(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  /** Deliver something that is not valid JSON. */
  serverSendRaw(data: string): void {
    this.onmessage?.({ data });
  }

  serverError(): void {
    this.onerror?.({});
  }

  /** The connection dropped without the client asking — 1006 is "abnormal". */
  serverDrop(code = 1006): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }

  /** Frames the app sent, parsed. */
  sentMessages(): Array<Record<string, unknown>> {
    return this.sent.map((raw) => JSON.parse(raw) as Record<string, unknown>);
  }
}

/** Install the fake as the global WebSocket. Undone by vi.unstubAllGlobals(). */
export function installFakeWebSocket(): typeof FakeWebSocket {
  FakeWebSocket.reset();
  vi.stubGlobal('WebSocket', FakeWebSocket);
  return FakeWebSocket;
}
