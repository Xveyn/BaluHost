/**
 * Hook for WebSocket-based real-time notifications
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import type { Notification } from '../api/notifications';
import { getWebSocketUrl, getWsToken } from '../api/notifications';
import { useAuth } from '../contexts/AuthContext';

export interface NotificationSocketState {
  connected: boolean;
  unreadCount: number;
  latestNotification: Notification | null;
  error: string | null;
}

export interface UseNotificationSocketOptions {
  enabled?: boolean;
  onNotification?: (notification: Notification) => void;
  onUnreadCountChange?: (count: number) => void;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

export function useNotificationSocket(options: UseNotificationSocketOptions = {}) {
  const {
    enabled = true,
    onNotification,
    onUnreadCountChange,
    reconnectDelay = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const { token } = useAuth();

  const [state, setState] = useState<NotificationSocketState>({
    connected: false,
    unreadCount: 0,
    latestNotification: null,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Refs for current values — keeps connect/disconnect stable (deps=[])
  const tokenRef = useRef(token);
  const enabledRef = useRef(enabled);
  const reconnectDelayRef = useRef(reconnectDelay);
  const maxReconnectAttemptsRef = useRef(maxReconnectAttempts);
  const onNotificationRef = useRef(onNotification);
  const onUnreadCountChangeRef = useRef(onUnreadCountChange);

  // Sync refs on every render
  useEffect(() => { tokenRef.current = token; }, [token]);
  useEffect(() => { enabledRef.current = enabled; }, [enabled]);
  useEffect(() => { reconnectDelayRef.current = reconnectDelay; }, [reconnectDelay]);
  useEffect(() => { maxReconnectAttemptsRef.current = maxReconnectAttempts; }, [maxReconnectAttempts]);
  useEffect(() => { onNotificationRef.current = onNotification; }, [onNotification]);
  useEffect(() => { onUnreadCountChangeRef.current = onUnreadCountChange; }, [onUnreadCountChange]);

  const connect = useCallback(async () => {
    if (!enabledRef.current || !tokenRef.current) return;

    // CONNECTING + OPEN + CLOSING guard — prevent duplicate WebSockets
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.CLOSING)
    ) {
      return;
    }

    try {
      // Fetch a short-lived, scoped WS token instead of passing the access token
      let wsToken: string;
      try {
        wsToken = await getWsToken();
      } catch {
        // If ws-token endpoint is unavailable (e.g. older backend), fall back to access token
        wsToken = tokenRef.current;
      }
      const url = getWebSocketUrl(wsToken);
      const ws = new WebSocket(url);

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
        setState((prev) => ({
          ...prev,
          connected: true,
          error: null,
        }));

        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case 'notification': {
              const notification = data.payload as Notification;
              setState((prev) => ({
                ...prev,
                latestNotification: notification,
              }));
              onNotificationRef.current?.(notification);
              break;
            }

            case 'unread_count': {
              const count = data.payload.count as number;
              setState((prev) => ({
                ...prev,
                unreadCount: count,
              }));
              onUnreadCountChangeRef.current?.(count);
              break;
            }

            case 'pong':
              // Heartbeat response, ignore
              break;

            default:
              break;
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        setState((prev) => ({
          ...prev,
          error: 'WebSocket error',
        }));
      };

      ws.onclose = (event) => {
        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        setState((prev) => ({
          ...prev,
          connected: false,
        }));

        // Only reconnect if this was the active connection
        if (wsRef.current === ws) {
          wsRef.current = null;

          // Attempt reconnection if not intentionally closed
          if (event.code !== 1000 && enabledRef.current) {
            if (reconnectAttemptsRef.current < maxReconnectAttemptsRef.current) {
              reconnectAttemptsRef.current++;
              const delay = reconnectDelayRef.current * reconnectAttemptsRef.current;
              reconnectTimeoutRef.current = setTimeout(() => {
                connect();
              }, delay);
            } else {
              setState((prev) => ({
                ...prev,
                error: 'Max reconnection attempts reached',
              }));
            }
          }
        }
      };

      wsRef.current = ws;
    } catch {
      setState((prev) => ({
        ...prev,
        connected: false,
        error: 'Connection failed',
      }));
    }
  }, []); // Stable identity — reads everything from refs

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }

    setState((prev) => ({
      ...prev,
      connected: false,
    }));
  }, []); // Stable identity

  const markRead = useCallback((notificationId: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'mark_read',
          payload: { notification_id: notificationId },
        })
      );
    }
  }, []);

  // 1) Mount: connect if ready. Unmount: disconnect.
  useEffect(() => {
    if (enabledRef.current && tokenRef.current) {
      void connect();
    }
    return () => { disconnect(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Runs ONCE on mount, cleanup on unmount

  // 2) Token became available after mount (e.g. slow AuthContext init)
  //    OR token removed (logout) → disconnect only.
  //    NO cleanup function → effect re-runs can't trigger disconnect.
  useEffect(() => {
    if (token && enabled) {
      void connect(); // no-op if already OPEN/CONNECTING
    } else if (!token) {
      disconnect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return {
    ...state,
    connect,
    disconnect,
    markRead,
    isConnected: state.connected,
  };
}

export default useNotificationSocket;
