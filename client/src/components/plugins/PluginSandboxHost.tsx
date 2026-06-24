// client/src/components/plugins/PluginSandboxHost.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';
import type { ThemePayload } from '../../lib/plugin-sandbox/protocol';

interface User { id: number; username: string; role: string }

interface Props {
  pluginName: string;
  user: User;
  grantedScopes: string[];
  theme?: ThemePayload;
}

const DEFAULT_THEME: ThemePayload = { name: 'dark', tokens: {} };

export default function PluginSandboxHost({ pluginName, user, grantedScopes, theme = DEFAULT_THEME }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const navigate = useNavigate();
  const [height, setHeight] = useState(480);

  // Derive stable primitive keys so the bridge is only recreated when the
  // plugin, user identity, or scope-list CONTENTS change — not on every
  // parent re-render that passes a new `[]` literal or a new user object ref.
  const scopesKey = grantedScopes.join(',');
  const userId = user.id;

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    // Read the CURRENT grantedScopes/user arrays/objects at effect-run time
    // (not the derived keys) so the bridge receives the real values.
    const bridge = new PluginBridge({
      iframe,
      pluginName,
      grantedScopes,
      user,
      theme,
      onResize: (h) => setHeight(Math.max(120, Math.ceil(h))),
      onNavigate: (path) => navigate(path),
    });
    bridge.start();
    return () => bridge.dispose();
    // `theme` intentionally omitted here — Task 4 wires live theme updates via a
    // separate effect + bridge.setTheme(); this file currently passes a default theme.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pluginName, scopesKey, userId, navigate]);

  return (
    <iframe
      ref={iframeRef}
      title={`plugin-${pluginName}`}
      src={`/api/plugins/${pluginName}/ui/host.html`}
      sandbox="allow-scripts"
      style={{ width: '100%', height, border: 'none' }}
    />
  );
}
