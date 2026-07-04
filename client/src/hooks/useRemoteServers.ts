import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/remote-servers';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';

/**
 * SSH server profiles — list via TanStack Query, CRUD + start via useMutation
 * (each onSettled invalidates the server-profiles list). User-scoped: the cache
 * is cleared on identity change (AuthContext). Public shape unchanged.
 */
export function useServerProfiles() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.remoteServers.serverProfiles(),
    queryFn: api.listServerProfiles,
  });

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: queryKeys.remoteServers.serverProfiles() }),
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: (data: api.ServerProfileCreate) => api.createServerProfile(data),
    onSettled: () => invalidate(),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<api.ServerProfileCreate> }) =>
      api.updateServerProfile(id, data),
    onSettled: () => invalidate(),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteServerProfile(id),
    onSettled: () => invalidate(),
  });
  const startMutation = useMutation({
    mutationFn: (id: number) => api.startRemoteServer(id),
    // Refresh so the server-provided last_used timestamp updates.
    onSettled: () => invalidate(),
  });

  const createProfile = useCallback(
    (data: api.ServerProfileCreate) => createMutation.mutateAsync(data),
    [createMutation],
  );
  const updateProfile = useCallback(
    (id: number, data: Partial<api.ServerProfileCreate>) => updateMutation.mutateAsync({ id, data }),
    [updateMutation],
  );
  const deleteProfile = useCallback(
    (id: number) => deleteMutation.mutateAsync(id),
    [deleteMutation],
  );
  const startServer = useCallback(
    (id: number) => startMutation.mutateAsync(id),
    [startMutation],
  );
  const testConnection = useCallback((id: number) => api.testSSHConnection(id), []);

  return {
    profiles: query.data ?? [],
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load profiles') : null,
    fetchProfiles: async () => {
      await query.refetch();
    },
    createProfile,
    updateProfile,
    deleteProfile,
    testConnection,
    startServer,
  };
}

/**
 * VPN profiles — same pattern as useServerProfiles (create/update via FormData,
 * testConnection is a passthrough with no cache effect).
 */
export function useVPNProfiles() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.remoteServers.vpnProfiles(),
    queryFn: api.listVPNProfiles,
  });

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: queryKeys.remoteServers.vpnProfiles() }),
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: (formData: FormData) => api.createVPNProfile(formData),
    onSettled: () => invalidate(),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, formData }: { id: number; formData: FormData }) =>
      api.updateVPNProfile(id, formData),
    onSettled: () => invalidate(),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteVPNProfile(id),
    onSettled: () => invalidate(),
  });

  const createProfile = useCallback(
    (formData: FormData) => createMutation.mutateAsync(formData),
    [createMutation],
  );
  const updateProfile = useCallback(
    (id: number, formData: FormData) => updateMutation.mutateAsync({ id, formData }),
    [updateMutation],
  );
  const deleteProfile = useCallback(
    (id: number) => deleteMutation.mutateAsync(id),
    [deleteMutation],
  );
  const testConnection = useCallback((id: number) => api.testVPNConnection(id), []);

  return {
    profiles: query.data ?? [],
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load VPN profiles') : null,
    fetchProfiles: async () => {
      await query.refetch();
    },
    createProfile,
    updateProfile,
    deleteProfile,
    testConnection,
  };
}
