import { useState, useEffect } from 'react';
import { ipcClient } from '../lib/ipc-client';
import type { RemoteServerProfile } from '../types/RemoteServerProfile';

export interface ServerOnlineStatus {
  profileId: number;
  online: boolean;
  lastChecked: Date;
  errorMessage?: string;
}

/**
 * Hook to check online status of multiple Remote Server profiles
 * Performs SSH connection test for each profile
 */
export function useServerOnlineStatus(profiles: RemoteServerProfile[], autoRefreshInterval?: number) {
  const [statusMap, setStatusMap] = useState<Map<number, ServerOnlineStatus>>(new Map());
  const [isLoading, setIsLoading] = useState(false);

  // Check status of a single server via HTTP health check
  const checkServerStatus = async (profile: RemoteServerProfile): Promise<ServerOnlineStatus> => {
    try {
      // Construct server URL with HTTP port (8000 for BaluHost)
      const serverUrl = `http://${profile.sshHost}:8000`;
      const result = await ipcClient.checkServerHealth(serverUrl);
      
      return {
        profileId: profile.id,
        online: result.connected === true,
        lastChecked: new Date(),
        errorMessage: result.message || (result.connected ? undefined : 'Server offline'),
      };
    } catch (error) {
      return {
        profileId: profile.id,
        online: false,
        lastChecked: new Date(),
        errorMessage: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  };

  // Check all profiles
  const checkAllServers = async (profilesToCheck: RemoteServerProfile[] = profiles) => {
    if (profilesToCheck.length === 0) return;
    
    setIsLoading(true);
    try {
      const results = await Promise.all(
        profilesToCheck.map(profile => checkServerStatus(profile))
      );
      
      const newStatusMap = new Map<number, ServerOnlineStatus>();
      results.forEach(status => {
        newStatusMap.set(status.profileId, status);
      });
      
      setStatusMap(newStatusMap);
    } finally {
      setIsLoading(false);
    }
  };

  // Initial check when profiles load
  useEffect(() => {
    if (profiles.length > 0) {
      checkAllServers(profiles);
    }
  }, [profiles.length]); // Only re-check if count changes

  // Optional auto-refresh
  useEffect(() => {
    if (!autoRefreshInterval || profiles.length === 0) return;

    const interval = setInterval(() => {
      checkAllServers(profiles);
    }, autoRefreshInterval);

    return () => clearInterval(interval);
  }, [autoRefreshInterval, profiles]);

  return {
    statusMap,
    isLoading,
    getStatus: (profileId: number) => statusMap.get(profileId),
    refreshStatus: checkAllServers,
  };
}
