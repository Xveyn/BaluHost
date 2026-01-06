import { useState, useCallback, useEffect } from 'react';
import { ipcClient, RemoteServerProfile } from '../lib/ipc-client';

export function useRemoteServerProfiles() {
  const [profiles, setProfiles] = useState<RemoteServerProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await ipcClient.getRemoteServerProfiles();
      setProfiles(data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load profiles');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const addProfile = useCallback(async (profile: Omit<RemoteServerProfile, 'id' | 'createdAt' | 'updatedAt'>) => {
    try {
      setError(null);
      await ipcClient.addRemoteServerProfile(profile);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const updateProfile = useCallback(async (profile: RemoteServerProfile) => {
    try {
      setError(null);
      await ipcClient.updateRemoteServerProfile(profile);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      setError(null);
      await ipcClient.deleteRemoteServerProfile(id);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const testConnection = useCallback(async (id: number) => {
    try {
      setError(null);
      return await ipcClient.testServerConnection(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to test connection';
      setError(message);
      throw err;
    }
  }, []);

  const startServer = useCallback(async (id: number) => {
    try {
      setError(null);
      return await ipcClient.startRemoteServer(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start server';
      setError(message);
      throw err;
    }
  }, []);

  return {
    profiles,
    loading,
    error,
    addProfile,
    updateProfile,
    deleteProfile,
    testConnection,
    startServer,
    refresh: loadProfiles,
  };
}
