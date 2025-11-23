import { buildApiUrl } from '../lib/api';

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

const getToken = (): string => {
  const token = localStorage.getItem('token');
  if (!token) {
    throw new Error('Keine aktive Sitzung – bitte erneut anmelden.');
  }
  return token;
};

const parseResponse = async <T>(response: Response): Promise<T> => {
  const text = await response.text();
  let payload: any = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.error || payload.message)) ||
      `Request failed with status ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : 'RAID request failed');
  }

  return payload as T;
};

export const getRaidStatus = async (): Promise<RaidStatusResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/status'), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return parseResponse<RaidStatusResponse>(response);
};

const postRaidAction = async (endpoint: string, array: string, device?: string): Promise<RaidActionResponse> => {
  const token = getToken();
  const payload: Record<string, string> = { array };
  if (device) {
    payload.device = device;
  }

  const response = await fetch(buildApiUrl(endpoint), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  return parseResponse<RaidActionResponse>(response);
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
  const token = getToken();

  const response = await fetch(buildApiUrl('/api/system/raid/options'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  return parseResponse<RaidActionResponse>(response);
};

export const getAvailableDisks = async (): Promise<AvailableDisksResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/available-disks'), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return parseResponse<AvailableDisksResponse>(response);
};

export const formatDisk = async (payload: FormatDiskPayload): Promise<RaidActionResponse> => {
  const token = getToken();

  const response = await fetch(buildApiUrl('/api/system/raid/format-disk'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  return parseResponse<RaidActionResponse>(response);
};

export const createArray = async (payload: CreateArrayPayload): Promise<RaidActionResponse> => {
  const token = getToken();

  const response = await fetch(buildApiUrl('/api/system/raid/create-array'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  return parseResponse<RaidActionResponse>(response);
};

export const deleteArray = async (payload: DeleteArrayPayload): Promise<RaidActionResponse> => {
  const token = getToken();

  const response = await fetch(buildApiUrl('/api/system/raid/delete-array'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  return parseResponse<RaidActionResponse>(response);
};
