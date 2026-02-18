import { apiClient } from '../lib/api';

export interface RaidDevice {
  name: string;
  state: string;
}

export interface RaidArray {
  name: string;
  level: string;
  size_bytes: number;
  status: string;
  devices: RaidDevice[];
  resync_progress?: number | null;
  bitmap?: string | null;
  sync_action?: string | null;
  cache?: import('./ssd-cache').CacheStatus | null;
}

export interface RaidStatusResponse {
  arrays: RaidArray[];
  speed_limits?: RaidSpeedLimits;
}

export interface RaidActionResponse {
  message: string;
}

export interface RaidSpeedLimits {
  minimum?: number | null;
  maximum?: number | null;
}

export interface RaidOptionsPayload {
  array: string;
  enable_bitmap?: boolean;
  add_spare?: string;
  remove_device?: string;
  write_mostly_device?: string;
  write_mostly?: boolean;
  set_speed_limit_min?: number;
  set_speed_limit_max?: number;
  trigger_scrub?: boolean;
}

export interface AvailableDisk {
  name: string;
  size_bytes: number;
  model?: string | null;
  is_partitioned: boolean;
  partitions: string[];
  in_raid: boolean;
  is_os_disk?: boolean;
  is_ssd?: boolean;
  is_cache_device?: boolean;
}

export interface AvailableDisksResponse {
  disks: AvailableDisk[];
}

export interface FormatDiskPayload {
  disk: string;
  filesystem?: string;
  label?: string;
}

export interface CreateArrayPayload {
  name: string;
  level: string;
  devices: string[];
  spare_devices?: string[];
}

export interface DeleteArrayPayload {
  array: string;
  force?: boolean;
}

export const getRaidStatus = async (): Promise<RaidStatusResponse> => {
  const { data } = await apiClient.get<RaidStatusResponse>('/api/system/raid/status');
  return data;
};

const postRaidAction = async (endpoint: string, array: string, device?: string): Promise<RaidActionResponse> => {
  const payload: Record<string, string> = { array };
  if (device) {
    payload.device = device;
  }
  const { data } = await apiClient.post<RaidActionResponse>(endpoint, payload);
  return data;
};

export const markDeviceFailed = async (array: string, device?: string): Promise<RaidActionResponse> => {
  return postRaidAction('/api/system/raid/degrade', array, device);
};

export const startRaidRebuild = async (array: string, device: string): Promise<RaidActionResponse> => {
  if (!device) {
    throw new Error('Es muss ein Gerät angegeben werden, um einen Rebuild zu starten.');
  }
  return postRaidAction('/api/system/raid/rebuild', array, device);
};

export const finalizeRaidRebuild = async (array: string): Promise<RaidActionResponse> => {
  return postRaidAction('/api/system/raid/finalize', array);
};

export const updateRaidOptions = async (payload: RaidOptionsPayload): Promise<RaidActionResponse> => {
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/options', payload);
  return data;
};

export const getAvailableDisks = async (): Promise<AvailableDisksResponse> => {
  const { data } = await apiClient.get<AvailableDisksResponse>('/api/system/raid/available-disks');
  return data;
};

export const formatDisk = async (payload: FormatDiskPayload): Promise<RaidActionResponse> => {
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/format-disk', payload);
  return data;
};

export const createArray = async (payload: CreateArrayPayload): Promise<RaidActionResponse> => {
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/create-array', payload);
  return data;
};

export const deleteArray = async (payload: DeleteArrayPayload): Promise<RaidActionResponse> => {
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/delete-array', payload);
  return data;
};

export const triggerRaidScrub = async (array?: string): Promise<RaidActionResponse> => {
  const body: Record<string, string | undefined> = {};
  if (array) body.array = array;
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/scrub', body);
  return data;
};

export interface ConfirmTokenResponse {
  token: string;
  expires_at: number;
}

export const requestConfirmation = async (action: string, payload: object, ttl_seconds?: number): Promise<ConfirmTokenResponse> => {
  const body: Record<string, unknown> = { action, payload };
  if (ttl_seconds) body.ttl_seconds = ttl_seconds;
  const { data } = await apiClient.post<ConfirmTokenResponse>('/api/system/raid/confirm/request', body);
  return data;
};

export const executeConfirmation = async (tokenStr: string): Promise<RaidActionResponse> => {
  const { data } = await apiClient.post<RaidActionResponse>('/api/system/raid/confirm/execute', { token: tokenStr });
  return data;
};
