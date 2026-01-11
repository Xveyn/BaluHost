// --- Remote Server Start API ---
import { apiClient } from '../lib/api';

export interface ServerProfile {
  id: number;
  user_id: number;
  name: string;
  ssh_host: string;
  ssh_port: number;
  ssh_username: string;
  vpn_profile_id?: number;
  power_on_command?: string;
  created_at: string;
  last_used?: string;
}

export interface ServerProfileCreate {
  name: string;
  ssh_host: string;
  ssh_port: number;
  ssh_username: string;
  ssh_private_key: string;
  vpn_profile_id?: number;
  power_on_command?: string;
}

export interface SSHConnectionTest {
  ssh_reachable: boolean;
  local_network: boolean;
  needs_vpn: boolean;
  error_message?: string;
}

export interface ServerStartResponse {
  profile_id: number;
  status: 'starting' | 'started' | 'error';
  message: string;
  timestamp?: string;
}

// Server Profile API
export async function createServerProfile(data: ServerProfileCreate): Promise<ServerProfile> {
  const res = await apiClient.post('/api/server-profiles', data);
  return res.data;
}

export async function listServerProfiles(): Promise<ServerProfile[]> {
  const res = await apiClient.get('/api/server-profiles');
  return res.data;
}

export async function getServerProfile(id: number): Promise<ServerProfile> {
  const res = await apiClient.get(`/api/server-profiles/${id}`);
  return res.data;
}

export async function updateServerProfile(id: number, data: Partial<ServerProfileCreate>): Promise<ServerProfile> {
  const res = await apiClient.put(`/api/server-profiles/${id}`, data);
  return res.data;
}

export async function deleteServerProfile(id: number): Promise<void> {
  await apiClient.delete(`/api/server-profiles/${id}`);
}

export async function testSSHConnection(id: number): Promise<SSHConnectionTest> {
  const res = await apiClient.post(`/api/server-profiles/${id}/check-connectivity`);
  return res.data;
}

export async function startRemoteServer(id: number): Promise<ServerStartResponse> {
  const res = await apiClient.post(`/api/server-profiles/${id}/start`);
  return res.data;
}

// --- VPN Profile API ---
export interface VPNProfile {
  id: number;
  user_id: number;
  name: string;
  vpn_type: 'openvpn' | 'wireguard' | 'custom';
  auto_connect: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface VPNConnectionTest {
  profile_id: number;
  connected: boolean;
  error_message?: string;
  timestamp?: string;
}

// VPN Profile API
export async function createVPNProfile(formData: FormData): Promise<VPNProfile> {
  const res = await apiClient.post('/api/vpn-profiles', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function listVPNProfiles(): Promise<VPNProfile[]> {
  const res = await apiClient.get('/api/vpn-profiles');
  return res.data;
}

export async function getVPNProfile(id: number): Promise<VPNProfile> {
  const res = await apiClient.get(`/api/vpn-profiles/${id}`);
  return res.data;
}

export async function updateVPNProfile(id: number, formData: FormData): Promise<VPNProfile> {
  const res = await apiClient.put(`/api/vpn-profiles/${id}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function deleteVPNProfile(id: number): Promise<void> {
  await apiClient.delete(`/api/vpn-profiles/${id}`);
}

export async function testVPNConnection(id: number): Promise<VPNConnectionTest> {
  const res = await apiClient.post(`/api/vpn-profiles/${id}/test-connection`);
  return res.data;
}
