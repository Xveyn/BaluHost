import { useState, useCallback, useEffect } from 'react';
import { ipcClient, VPNProfile } from '../lib/ipc-client';

export function useVPNProfiles() {
  const [profiles, setProfiles] = useState<VPNProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await ipcClient.getVPNProfiles();
      // Extract profiles array from response
      const profilesArray = Array.isArray(response) ? response : (response?.data?.profiles || response?.profiles || []);
      setProfiles(profilesArray);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load VPN profiles');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const addProfile = useCallback(async (profile: Omit<VPNProfile, 'id' | 'createdAt' | 'updatedAt'>) => {
    try {
      setError(null);
      await ipcClient.addVPNProfile(profile);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add VPN profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const updateProfile = useCallback(async (profile: VPNProfile) => {
    try {
      setError(null);
      await ipcClient.updateVPNProfile(profile);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update VPN profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      setError(null);
      await ipcClient.deleteVPNProfile(id);
      await loadProfiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete VPN profile';
      setError(message);
      throw err;
    }
  }, [loadProfiles]);

  const testConnection = useCallback(async (id: number) => {
    try {
      setError(null);
      return await ipcClient.testVPNConnection(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to test VPN connection';
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
    refresh: loadProfiles,
  };
}
