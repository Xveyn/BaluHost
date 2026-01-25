import { useState, useEffect } from 'react';
import { ipcClient } from '../lib/ipc-client';

export interface DiscoveredServer {
  hostname: string;
  ipAddress: string;
  port: number;
  sshPort: number;
  username?: string;
  description?: string;
  discoveredAt: string;
}

export function useDiscoverServers(autoRefresh?: boolean) {
  const [servers, setServers] = useState<DiscoveredServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const discoverNetworkServers = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await ipcClient.sendMessage({
        type: 'discover_network_servers',
      });

      if (result.success && result.data?.servers) {
        setServers(result.data.servers);
      } else {
        setError(result.error || 'Failed to discover servers');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error('Network discovery error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Auto-discover on mount if enabled
  useEffect(() => {
    if (autoRefresh !== false) {
      discoverNetworkServers();
    }
  }, []);

  // Optional auto-refresh
  useEffect(() => {
    if (!autoRefresh || autoRefresh < 5000) return;

    const interval = setInterval(discoverNetworkServers, autoRefresh);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  return {
    servers,
    loading,
    error,
    refresh: discoverNetworkServers,
  };
}
