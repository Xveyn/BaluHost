// client/src/components/plugins/PluginSandboxHost.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

interface User { id: number; username: string; role: string }

interface Props {
  pluginName: string;
  user: User;
  grantedScopes: string[];
}

export default function PluginSandboxHost({ pluginName, user, grantedScopes }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const navigate = useNavigate();
  const [height, setHeight] = useState(480);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const bridge = new PluginBridge({
      iframe,
      pluginName,
      grantedScopes,
      user,
      onResize: (h) => setHeight(Math.max(120, Math.ceil(h))),
      onNavigate: (path) => navigate(path),
    });
    bridge.start();
    return () => bridge.dispose();
  }, [pluginName, grantedScopes, user, navigate]);

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
