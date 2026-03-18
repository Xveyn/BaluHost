/**
 * Generic Dashboard Plugin Panel
 *
 * Fetches the active plugin's panel spec+data via REST, subscribes to
 * WebSocket updates, and renders the appropriate panel renderer.
 * Falls back to REST polling (10s) if WS disconnects.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { buildApiUrl, apiClient } from '../../lib/api';
import * as LucideIcons from 'lucide-react';
import { GaugePanel } from './panels/GaugePanel';
import { StatPanel } from './panels/StatPanel';
import { StatusPanel } from './panels/StatusPanel';
import { ChartPanel } from './panels/ChartPanel';
import { PanelPlaceholder } from './panels/PanelPlaceholder';

interface PanelSpec {
  plugin_name: string;
  panel_type: 'gauge' | 'stat' | 'status' | 'chart';
  title: string;
  icon: string;
  accent: string;
  data: Record<string, unknown> | null;
}

const REST_POLL_INTERVAL = 10_000; // 10s fallback when WS is down

export const PluginDashboardPanel: React.FC = () => {
  const { token } = useAuth();
  const [panel, setPanel] = useState<PanelSpec | null>(null);
  const [loaded, setLoaded] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch panel data via REST
  const fetchPanel = useCallback(async () => {
    try {
      const res = await apiClient.get<PanelSpec | null>('/api/dashboard/plugin-panel');
      setPanel(res.data);
    } catch {
      // Silent fail — panel slot stays empty
    } finally {
      setLoaded(true);
    }
  }, []);

  // Initial REST fetch
  useEffect(() => {
    fetchPanel();
  }, [fetchPanel]);

  // WebSocket subscription for live updates
  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}${buildApiUrl('/api/notifications/ws')}?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type: string;
          payload?: unknown;
        };

        if (msg.type === 'dashboard_panel_update' && msg.payload) {
          const payload = msg.payload as {
            panel_type: string;
            plugin_name: string;
            data: Record<string, unknown>;
          };

          setPanel((prev) => {
            if (!prev) return prev;
            // Only update data if it's for the same plugin
            if (prev.plugin_name !== payload.plugin_name) return prev;
            return { ...prev, data: payload.data };
          });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onopen = () => {
      // WS connected — stop REST polling fallback
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    ws.onclose = () => {
      // WS disconnected — start REST polling fallback
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchPanel, REST_POLL_INTERVAL);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [token, fetchPanel]);

  if (!loaded) {
    return (
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Plugin Panel</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">...</p>
        </div>
      </div>
    );
  }

  if (!panel || !panel.data) {
    return <PanelPlaceholder />;
  }

  // Resolve Lucide icon by name
  const iconKey = panel.icon.charAt(0).toUpperCase() + panel.icon.slice(1);
  const IconComponent = (LucideIcons as unknown as Record<string, React.FC<{ className?: string }>>)[iconKey]
    || (LucideIcons.Plug as unknown as React.FC<{ className?: string }>);
  const iconElement = <IconComponent className="h-6 w-6" />;

  const rendererProps = {
    title: panel.title,
    icon: iconElement,
    accent: panel.accent,
  };

  switch (panel.panel_type) {
    case 'gauge':
      return <GaugePanel {...rendererProps} data={panel.data as any} />;
    case 'stat':
      return <StatPanel {...rendererProps} data={panel.data as any} />;
    case 'status':
      return <StatusPanel {...rendererProps} data={panel.data as any} />;
    case 'chart':
      return <ChartPanel {...rendererProps} data={panel.data as any} />;
    default:
      return <PanelPlaceholder />;
  }
};
