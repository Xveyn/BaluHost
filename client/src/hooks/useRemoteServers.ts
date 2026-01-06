import { useState, useCallback, useEffect } from 'react';
import { useToast } from '@/components/ui/use-toast';
import * as api from '@/api/remote-servers';

export function useServerProfiles() {
  const [profiles, setProfiles] = useState<api.ServerProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listServerProfiles();
      setProfiles(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load profiles';
      setError(message);
      toast({ title: 'Error', description: message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const createProfile = useCallback(async (data: api.ServerProfileCreate) => {
    try {
      const newProfile = await api.createServerProfile(data);
      setProfiles([newProfile, ...profiles]);
      toast({ title: 'Success', description: 'Server profile created' });
      return newProfile;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const updateProfile = useCallback(async (id: number, data: Partial<api.ServerProfileCreate>) => {
    try {
      const updated = await api.updateServerProfile(id, data);
      setProfiles(profiles.map(p => p.id === id ? updated : p));
      toast({ title: 'Success', description: 'Profile updated' });
      return updated;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      await api.deleteServerProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
      toast({ title: 'Success', description: 'Profile deleted' });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const testConnection = useCallback(async (id: number) => {
    try {
      return await api.testSSHConnection(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection test failed';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [toast]);

  const startServer = useCallback(async (id: number) => {
    try {
      const result = await api.startRemoteServer(id);
      // Update last_used timestamp
      const profile = profiles.find(p => p.id === id);
      if (profile) {
        profile.last_used = new Date().toISOString();
        setProfiles([...profiles]);
      }
      toast({ title: 'Success', description: result.message });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start server';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

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
  const { toast } = useToast();

  const fetchProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listVPNProfiles();
      setProfiles(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load VPN profiles';
      setError(message);
      toast({ title: 'Error', description: message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const createProfile = useCallback(async (formData: FormData) => {
    try {
      const newProfile = await api.createVPNProfile(formData);
      setProfiles([newProfile, ...profiles]);
      toast({ title: 'Success', description: 'VPN profile created' });
      return newProfile;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create VPN profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const updateProfile = useCallback(async (id: number, formData: FormData) => {
    try {
      const updated = await api.updateVPNProfile(id, formData);
      setProfiles(profiles.map(p => p.id === id ? updated : p));
      toast({ title: 'Success', description: 'VPN profile updated' });
      return updated;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update VPN profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const deleteProfile = useCallback(async (id: number) => {
    try {
      await api.deleteVPNProfile(id);
      setProfiles(profiles.filter(p => p.id !== id));
      toast({ title: 'Success', description: 'VPN profile deleted' });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete VPN profile';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [profiles, toast]);

  const testConnection = useCallback(async (id: number) => {
    try {
      return await api.testVPNConnection(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'VPN test failed';
      toast({ title: 'Error', description: message, variant: 'destructive' });
      throw err;
    }
  }, [toast]);

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
