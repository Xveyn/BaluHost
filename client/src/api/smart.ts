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

export interface SmartSelfTest {
  test_type: string;
  status: string;
  passed: boolean;
  power_on_hours: number;
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
  last_self_test: SmartSelfTest | null;
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

export interface SmartModeResponse {
  mode: string;
  message?: string;
}

export async function getSmartMode(): Promise<SmartModeResponse> {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/smart/mode'), {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'SMART-Modus konnte nicht abgerufen werden');
  }

  return await response.json();
}

export async function toggleSmartMode(): Promise<SmartModeResponse> {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/smart/toggle-mode'), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'SMART-Modus konnte nicht geändert werden');
  }

  return await response.json();
}

export interface SmartTestPayload {
  device?: string;
  type?: string;
}

export async function runSmartTest(payload: SmartTestPayload = {}): Promise<{ message: string }> {
  const token = getToken();
  const response = await fetch(buildApiUrl('/api/system/smart/test'), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'SMART-Test konnte nicht gestartet werden');
  }

  return await response.json();
}
