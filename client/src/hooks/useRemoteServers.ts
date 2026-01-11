import { useState, useCallback, useEffect } from 'react';
import * as api from '../api/remote-servers';

export function useServerProfiles() {
  const [profiles, setProfiles] = useState<api.ServerProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listServerProfiles();
      setProfiles(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load profiles';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const createProfile = useCallback(async (data: api.ServerProfileCreate) => {
    try {
      const newProfile = await api.createServerProfile(data);
      setProfiles([newProfile, ...profiles]);
      return newProfile;
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const updateProfile = useCallback(async (id: number, data: Partial<api.ServerProfileCreate>) => {
    try {
      const updated = await api.updateServerProfile(id, data);
      setProfiles(profiles.map(p => p.id === id ? updated : p));
      return updated;
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      await api.deleteServerProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const testConnection = useCallback(async (id: number) => {
    try {
      return await api.testSSHConnection(id);
    } catch (err) {
      throw err;
    }
  }, []);

  const startServer = useCallback(async (id: number) => {
    try {
      const result = await api.startRemoteServer(id);
      // Update last_used timestamp
      const profile = profiles.find(p => p.id === id);
      if (profile) {
        profile.last_used = new Date().toISOString();
        setProfiles([...profiles]);
      }
      return result;
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  return {
    profiles,
    loading,
    error,
    fetchProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
    testConnection,
    startServer,
  };
}

export function useVPNProfiles() {
  const [profiles, setProfiles] = useState<api.VPNProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listVPNProfiles();
      setProfiles(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load VPN profiles';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const createProfile = useCallback(async (formData: FormData) => {
    try {
      const newProfile = await api.createVPNProfile(formData);
      setProfiles([newProfile, ...profiles]);
      return newProfile;
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const updateProfile = useCallback(async (id: number, formData: FormData) => {
    try {
      const updated = await api.updateVPNProfile(id, formData);
      setProfiles(profiles.map(p => p.id === id ? updated : p));
      return updated;
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      await api.deleteVPNProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
    } catch (err) {
      throw err;
    }
  }, [profiles]);

  const testConnection = useCallback(async (id: number) => {
    try {
      return await api.testVPNConnection(id);
    } catch (err) {
      throw err;
    }
  }, []);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  return {
    profiles,
    loading,
    error,
    fetchProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
    testConnection,
  };
}
