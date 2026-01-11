import React from 'react';
import { Plus, Wifi, WifiOff, RefreshCw, AlertCircle } from 'lucide-react';
import { useDiscoverServers, type DiscoveredServer } from '../../hooks/useDiscoverServers';
import type { RemoteServerProfile } from '../../types/RemoteServerProfile';

interface AvailableServersProps {
  onAddServer: (server: DiscoveredServer) => void;
  savedServerHosts: Set<string>;
}

/**
 * Panel showing servers discovered on the local network
 * Allows users to quickly add them to their saved profiles
 */
export function AvailableServers({ onAddServer, savedServerHosts }: AvailableServersProps) {
  const { servers, loading, error, refresh } = useDiscoverServers(false); // Manual refresh only

  const unsavedServers = servers.filter(s => !savedServerHosts.has(s.hostname));

  if (error) {
    return (
      <div className="rounded-lg border border-red-700/50 bg-red-900/20 p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertCircle size={16} />
          <span className="text-sm">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300 flex items-center gap-2">
          <Wifi size={16} />
          Available Servers in Network
        </h3>
        <button
          onClick={refresh}
          disabled={loading}
          className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 
            hover:text-slate-100 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Scan
        </button>
      </div>

      {loading ? (
        <div className="p-4 text-center text-slate-400 text-sm">
          Scanning network...
        </div>
      ) : unsavedServers.length === 0 ? (
        <div className="p-4 text-center text-slate-400 text-sm border border-slate-700 rounded">
          {servers.length === 0 ? (
            <p>No servers discovered. Click Scan to search the network.</p>
          ) : (
            <p>All discovered servers are already saved!</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {unsavedServers.map((server) => (
            <div
              key={server.hostname}
              className="flex items-center justify-between p-3 rounded-lg border border-slate-700 
                bg-slate-800/50 hover:bg-slate-800/70 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Wifi size={14} className="text-green-400 flex-shrink-0" />
                  <span className="font-medium text-slate-200 truncate">{server.hostname}</span>
                </div>
                <div className="text-xs text-slate-400 mt-1 ml-6">
                  {server.ipAddress}:{server.sshPort} {server.description && `• ${server.description}`}
                </div>
                <div className="text-[10px] text-slate-500 mt-1 ml-6">
                  Discovered: {new Date(server.discoveredAt).toLocaleTimeString()}
                </div>
              </div>
              <button
                onClick={() => onAddServer(server)}
                className="ml-2 px-3 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white 
                  text-xs font-medium flex items-center gap-1 flex-shrink-0 transition-colors"
              >
                <Plus size={14} />
                Add
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
