/**
 * BaluPi dashboard endpoints (Pi build only).
 *
 * Thin typed wrappers around the handshake / energy / system endpoints the
 * PiDashboard reads, plus the Wake-on-LAN trigger. Consumed by the
 * `usePiDashboardData` hook (TanStack Query).
 */
import { apiClient } from '../lib/api';

export interface HandshakeStatus {
  nas_state: string;
  since: string | null;
  last_snapshot: string | null;
  inbox_size_mb: number;
  inbox_files: number;
}

export interface EnergyDevice {
  device_id: string;
  name: string;
  power_w: number;
  voltage_v: number;
  current_a: number;
}

export interface EnergyCurrent {
  devices: EnergyDevice[];
  total_power_w: number;
}

export interface PiSystem {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  temperature_c: number | null;
  uptime_seconds: number;
  hostname: string;
}

export interface SnapshotData {
  version: number;
  generated_at: string;
  baluhost_version: string;
  system: {
    hostname: string;
    uptime_seconds: number;
    cpu_model: string;
    ram_total_gb: number;
  };
  storage: {
    arrays: Array<{
      name: string;
      level: string;
      state: string;
      size_bytes: number;
      devices: string[];
    }>;
    total_bytes: number;
    used_bytes: number;
  };
  smart_health: Record<string, {
    status: string;
    temperature_c: number | null;
    power_on_hours: number | null;
  }>;
  services: {
    vpn: { active_clients: number };
    shares: { active_shares: number };
    backups: { last_backup: string | null; status: string };
  };
  users: {
    total: number;
    list: Array<{ username: string; role: string }>;
  };
  files_summary: {
    total_files: number;
    total_size_bytes: number;
  };
}

export async function getHandshakeStatus(): Promise<HandshakeStatus> {
  const { data } = await apiClient.get<HandshakeStatus>('/api/handshake/status');
  return data;
}

export async function getPiEnergyCurrent(): Promise<EnergyCurrent> {
  const { data } = await apiClient.get<EnergyCurrent>('/api/energy/current');
  return data;
}

export async function getPiSystemStatus(): Promise<PiSystem> {
  const { data } = await apiClient.get<PiSystem>('/api/system/status');
  return data;
}

export async function getHandshakeSnapshot(): Promise<SnapshotData> {
  const { data } = await apiClient.get<SnapshotData>('/api/handshake/snapshot');
  return data;
}

export async function sendNasWol(): Promise<void> {
  await apiClient.post('/api/nas/wol');
}
