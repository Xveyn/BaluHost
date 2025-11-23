import { buildApiUrl } from '../lib/api';

export interface SmartAttribute {
  id: number;
  name: string;
  value: number;
  worst: number;
  threshold: number;
  raw: string;
  status: string;
}

export interface SmartDevice {
  name: string;
  model: string;
  serial: string;
  temperature: number | null;
  status: string;
  capacity_bytes: number | null;
  used_bytes: number | null;
  used_percent: number | null;
  mount_point: string | null;
  attributes: SmartAttribute[];
}

export interface SmartStatusResponse {
  checked_at: string;
  devices: SmartDevice[];
}

const getToken = (): string => {
  const token = localStorage.getItem('token');
  if (!token) {
    throw new Error('Keine aktive Sitzung – bitte erneut anmelden.');
  }
  return token;
};

export async function fetchSmartStatus(): Promise<SmartStatusResponse> {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/smart/status'), {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'SMART-Status konnte nicht abgerufen werden');
  }

  return await response.json();
}
