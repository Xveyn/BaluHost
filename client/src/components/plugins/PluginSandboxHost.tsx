// client/src/components/plugins/PluginSandboxHost.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';
import { useTheme, themes } from '../../contexts/ThemeContext';

interface User { id: number; username: string; role: string }

interface Props {
  pluginName: string;
  user: User;
  grantedScopes: string[];
  minRuntimeAbi?: number;
}

export default function PluginSandboxHost({ pluginName, user, grantedScopes, minRuntimeAbi }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const bridgeRef = useRef<PluginBridge | null>(null);
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [height, setHeight] = useState(480);
  const [error, setError] = useState<string | null>(null);

  // Derive stable primitive keys so the bridge is only recreated when the
  // plugin, user identity, or scope-list CONTENTS change — not on every
  // parent re-render that passes a new `[]` literal or a new user object ref.
  const scopesKey = grantedScopes.join(',');
  const userId = user.id;

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    setError(null);
    const bridge = new PluginBridge({
      iframe,
      pluginName,
      grantedScopes,
      user,
      minRuntimeAbi,
      theme: { name: theme, tokens: themes[theme].colors },
      onResize: (h) => setHeight(Math.max(120, Math.ceil(h))),
      onNavigate: (path) => navigate(path),
      onError: (code) => setError(code),
    });
    bridge.start();
    bridgeRef.current = bridge;
    return () => { bridge.dispose(); bridgeRef.current = null; };
    // `theme` intentionally omitted — live theme changes are pushed via the
    // separate effect below using bridge.setTheme() without recreating the bridge.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pluginName, scopesKey, userId, minRuntimeAbi, navigate]);

  // Push theme changes WITHOUT recreating the bridge (which would reload the iframe).
  useEffect(() => {
    bridgeRef.current?.setTheme({ name: theme, tokens: themes[theme].colors });
  }, [theme]);

  if (error === 'abi_mismatch') {
    return (
      <div className="p-6 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm">
        This plugin needs a newer BaluHost runtime.
      </div>
    );
  }

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
