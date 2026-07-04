import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useServerProfiles, useVPNProfiles } from '../../hooks/useRemoteServers';
import * as remoteApi from '../../api/remote-servers';
import type { ServerProfile, VPNProfile } from '../../api/remote-servers';

vi.mock('../../api/remote-servers');
const api = vi.mocked(remoteApi);

const serverProfile: ServerProfile = {
  id: 1,
  user_id: 1,
  name: 'NAS',
  ssh_host: '10.0.0.1',
  ssh_port: 22,
  ssh_username: 'admin',
  created_at: '2026-01-01T00:00:00Z',
};

const vpnProfile: VPNProfile = {
  id: 1,
  user_id: 1,
  name: 'Home VPN',
  vpn_type: 'wireguard',
  auto_connect: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listServerProfiles.mockResolvedValue([serverProfile]);
  api.listVPNProfiles.mockResolvedValue([vpnProfile]);
});

describe('useServerProfiles', () => {
  it('loads the profile list', async () => {
    const { result } = renderHook(() => useServerProfiles(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profiles).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('createProfile calls the API, returns the profile and refetches', async () => {
    api.createServerProfile.mockResolvedValue({ ...serverProfile, id: 2, name: 'New' });
    const { result } = renderHook(() => useServerProfiles(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = api.listServerProfiles.mock.calls.length;

    let created: ServerProfile | undefined;
    await act(async () => {
      created = await result.current.createProfile({
        name: 'New',
        ssh_host: '10.0.0.2',
        ssh_port: 22,
        ssh_username: 'admin',
        ssh_private_key: 'KEY',
      });
    });

    expect(api.createServerProfile).toHaveBeenCalled();
    expect(created?.id).toBe(2);
    await waitFor(() => expect(api.listServerProfiles.mock.calls.length).toBeGreaterThan(before));
  });

  it('surfaces an error string when the list fetch fails', async () => {
    api.listServerProfiles.mockReset();
    api.listServerProfiles.mockRejectedValue(new Error('profiles boom'));
    const { result } = renderHook(() => useServerProfiles(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.error).toBe('profiles boom'));
  });
});

describe('useVPNProfiles', () => {
  it('loads the VPN profile list', async () => {
    const { result } = renderHook(() => useVPNProfiles(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profiles).toHaveLength(1);
  });

  it('createProfile posts the FormData and refetches', async () => {
    api.createVPNProfile.mockResolvedValue({ ...vpnProfile, id: 2 });
    const { result } = renderHook(() => useVPNProfiles(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = api.listVPNProfiles.mock.calls.length;

    const fd = new FormData();
    await act(async () => {
      await result.current.createProfile(fd);
    });

    expect(api.createVPNProfile).toHaveBeenCalledWith(fd);
    await waitFor(() => expect(api.listVPNProfiles.mock.calls.length).toBeGreaterThan(before));
  });
});
