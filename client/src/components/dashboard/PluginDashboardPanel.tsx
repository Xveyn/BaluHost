/**
 * Generic Dashboard Plugin Panel
 *
 * Fetches the active plugin's panel spec+data via REST, polls it every 10s,
 * and additionally subscribes to WebSocket updates for faster refreshes.
 *
 * The poll is the floor, the socket only an accelerator: panel updates are
 * broadcast by the primary Uvicorn worker alone, and a broadcast reaches only
 * sockets in that process (#306). A socket that lands on another worker
 * connects fine and then stays silent - so the poll must not stop on onopen.
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { buildApiUrl, apiClient } from '../../lib/api';
import { getWsToken } from '../../api/notifications';
import * as LucideIcons from 'lucide-react';
import { GaugePanel } from './panels/GaugePanel';
import { StatPanel } from './panels/StatPanel';
import { StatusPanel } from './panels/StatusPanel';
import { ChartPanel } from './panels/ChartPanel';
import { PanelPlaceholder } from './panels/PanelPlaceholder';
import { resolvePluginString } from '../../lib/pluginI18n';
import type { PluginTranslations } from '../../api/plugins';

interface PanelSpec {
  plugin_name: string;
  panel_type: 'gauge' | 'stat' | 'status' | 'chart';
  title: string;
  icon: string;
  accent: string;
  data: Record<string, unknown> | null;
  translations?: PluginTranslations;
}

const REST_POLL_INTERVAL = 10_000; // 10s, runs whether or not the socket is open

// Plugin name → navigation target when panel is clicked
const PANEL_CLICK_TARGETS: Record<string, string> = {
  tapo_smart_plug: '/system?tab=power',
};

export const PluginDashboardPanel: React.FC = () => {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [panel, setPanel] = useState<PanelSpec | null>(null);
  const [loaded, setLoaded] = useState(false);

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

  // REST polling - always on while signed in, socket or not (see header, #306)
  useEffect(() => {
    if (!token) return;
    const poll = setInterval(fetchPanel, REST_POLL_INTERVAL);
    return () => clearInterval(poll);
  }, [token, fetchPanel]);

  // WebSocket subscription for faster updates
  useEffect(() => {
    if (!token) return;
    // Tauri Companion: the Rust HTTP→UDS proxy can't relay WebSocket
    // upgrades yet, and `window.location.host` resolves to `tauri.localhost`
    // which produces a malformed WS URL that crashes the constructor.
    // The REST poll above covers it.
    if (typeof window !== 'undefined' && window.__BALU_API_BASE__) return;

    // The token fetch is async: an unmount (or a StrictMode re-run) that
    // happens before it resolves must not open a socket nobody closes.
    let cancelled = false;
    let ws: WebSocket | null = null;

    void (async () => {
      let wsToken: string;
      try {
        // The endpoint accepts only a short-lived, scoped ws token. The access
        // token is rejected fail-closed - in the ?token= query it would end up
        // in proxy logs (#618). No socket without one; the poll covers it.
        wsToken = await getWsToken();
      } catch {
        return;
      }
      if (cancelled) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}${buildApiUrl('/api/notifications/ws')}?token=${encodeURIComponent(wsToken)}`;

      try {
        ws = new WebSocket(wsUrl);
      } catch {
        // Constructor can throw (malformed URL, insecure context). Stay on
        // the REST poll instead of bubbling to the ErrorBoundary.
        return;
      }

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
    })();

    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [token]);

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

  // Resolve Lucide icon by name (kebab-case to PascalCase, e.g. "hard-drive" -> "HardDrive")
  const iconKey = panel.icon
    .split('-')
    .map(s => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  const IconComponent = (LucideIcons as unknown as Record<string, React.FC<{ className?: string }>>)[iconKey]
    || (LucideIcons.Plug as unknown as React.FC<{ className?: string }>);
  const iconElement = <IconComponent className="h-6 w-6" />;

  const clickTarget = PANEL_CLICK_TARGETS[panel.plugin_name];
  const handleClick = clickTarget ? () => navigate(clickTarget) : undefined;

  const rendererProps = {
    title: resolvePluginString(panel.translations, 'panel_title', panel.title),
    icon: iconElement,
    accent: panel.accent,
    onClick: handleClick,
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
