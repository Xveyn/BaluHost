import { buildApiUrl } from '../lib/api';
import type { RaidActionResponse } from './raid';

export type CacheMode = 'writethrough' | 'writeback' | 'writearound' | 'none';

export interface CacheStatus {
  array_name: string;
  cache_device: string;
  bcache_device: string | null;
  mode: CacheMode;
  state: string;
  hit_rate_percent: number | null;
  dirty_data_bytes: number;
  cache_size_bytes: number;
  cache_used_bytes: number;
  sequential_cutoff_bytes: number;
}

export interface CacheAttachPayload {
  array: string;
  cache_device: string;
  mode?: CacheMode;
}

export interface CacheDetachPayload {
  array: string;
  force?: boolean;
}

export interface CacheConfigurePayload {
  array: string;
  mode?: CacheMode;
  sequential_cutoff_bytes?: number;
}

export interface ExternalBitmapPayload {
  array: string;
  ssd_partition: string;
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
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.error || payload.message)) ||
      `Request failed with status ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : 'SSD cache request failed');
  }

  return payload as T;
};

export const getCacheStatuses = async (): Promise<CacheStatus[]> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/cache/status'), {
    headers: { Authorization: `Bearer ${token}` },
  });
  return parseResponse<CacheStatus[]>(response);
};

export const getCacheStatus = async (array: string): Promise<CacheStatus> => {
  const token = getToken();
  const response = await fetch(buildApiUrl(`/api/system/raid/cache/status/${encodeURIComponent(array)}`), {
    headers: { Authorization: `Bearer ${token}` },
  });
  return parseResponse<CacheStatus>(response);
};

export const attachCache = async (payload: CacheAttachPayload): Promise<RaidActionResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/cache/attach'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<RaidActionResponse>(response);
};

export const detachCache = async (payload: CacheDetachPayload): Promise<RaidActionResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/cache/detach'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<RaidActionResponse>(response);
};

export const configureCache = async (payload: CacheConfigurePayload): Promise<RaidActionResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/cache/configure'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<RaidActionResponse>(response);
};

export const setExternalBitmap = async (payload: ExternalBitmapPayload): Promise<RaidActionResponse> => {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/raid/cache/external-bitmap'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<RaidActionResponse>(response);
};
