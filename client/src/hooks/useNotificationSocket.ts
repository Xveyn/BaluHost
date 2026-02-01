/**
 * Hook for WebSocket-based real-time notifications
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import type { Notification } from '../api/notifications';
import { getWebSocketUrl } from '../api/notifications';

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

  // Use refs for callbacks to avoid reconnection on every render
  const onNotificationRef = useRef(onNotification);
  const onUnreadCountChangeRef = useRef(onUnreadCountChange);

  // Update refs when callbacks change
  useEffect(() => {
    onNotificationRef.current = onNotification;
  }, [onNotification]);

  useEffect(() => {
    onUnreadCountChangeRef.current = onUnreadCountChange;
  }, [onUnreadCountChange]);

  const connect = useCallback(() => {
    if (!enabled) return;

    // Don't create duplicate connections
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[NotificationSocket] Already connected, skipping');
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
      setState((prev) => ({
        ...prev,
        connected: false,
        error: 'No authentication token',
      }));
      return;
    }

    try {
      const url = getWebSocketUrl();
      console.log('[NotificationSocket] Connecting to:', url.replace(/token=.*/, 'token=***'));
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('[NotificationSocket] Connected');
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
            case 'notification':
              const notification = data.payload as Notification;
              setState((prev) => ({
                ...prev,
                latestNotification: notification,
              }));
              onNotificationRef.current?.(notification);
              break;

            case 'unread_count':
              const count = data.payload.count as number;
              setState((prev) => ({
                ...prev,
                unreadCount: count,
              }));
              onUnreadCountChangeRef.current?.(count);
              break;

            case 'pong':
              // Heartbeat response, ignore
              break;

            default:
              console.log('[NotificationSocket] Unknown message type:', data.type);
          }
        } catch (error) {
          console.error('[NotificationSocket] Failed to parse message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[NotificationSocket] Error:', error);
        setState((prev) => ({
          ...prev,
          error: 'WebSocket error',
        }));
      };

      ws.onclose = (event) => {
        console.log('[NotificationSocket] Disconnected:', event.code, event.reason);

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
          if (event.code !== 1000 && enabled) {
            if (reconnectAttemptsRef.current < maxReconnectAttempts) {
              reconnectAttemptsRef.current++;
              const delay = reconnectDelay * reconnectAttemptsRef.current;
              console.log(`[NotificationSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

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
    } catch (error) {
      console.error('[NotificationSocket] Connection failed:', error);
      setState((prev) => ({
        ...prev,
        connected: false,
        error: 'Connection failed',
      }));
    }
  }, [enabled, reconnectDelay, maxReconnectAttempts]);

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
  }, []);

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

  // Connect on mount, disconnect on unmount
  // Note: connect/disconnect are stable now (don't depend on callbacks)
  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Reconnect when token changes
  useEffect(() => {
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === 'token') {
        disconnect();
        if (event.newValue) {
          connect();
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [connect, disconnect]);

  return {
    ...state,
    connect,
    disconnect,
    markRead,
    isConnected: state.connected,
  };
}

export default useNotificationSocket;
