/**
 * API-Client der Bluetooth-Steuerung (bundled Plugin `bluetooth`).
 *
 * Alle Routen liegen hinter dem Recht `can_manage_bluetooth` — auch die
 * lesenden, weil die Liste Hardware und MAC-Adressen verrät. Koppeln und
 * Bestätigen lehnt der Server außerhalb privater Netze ab; `can_pair_here`
 * sagt der UI das vorab.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/bluetooth';

export type DeviceKind = 'controller' | 'audio' | 'input' | 'other';

export type PairingStage =
  | 'connecting'
  | 'display_passkey'
  | 'display_pin'
  | 'confirm'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export const TERMINAL_STAGES: ReadonlySet<PairingStage> = new Set<PairingStage>([
  'succeeded',
  'failed',
  'cancelled',
]);

export interface BluetoothAdapter {
  address: string;
  name: string;
  powered: boolean;
  /** Auch true, wenn KDE gerade scannt. */
  discovering: boolean;
}

export interface BluetoothDevice {
  address: string;
  name: string;
  kind: DeviceKind;
  icon: string | null;
  paired: boolean;
  trusted: boolean;
  connected: boolean;
  battery_percent: number | null;
  rssi: number | null;
}

export interface BluetoothState {
  available: boolean;
  detail: string | null;
  warning: string | null;
  adapter: BluetoothAdapter | null;
  devices: BluetoothDevice[];
  can_pair_here: boolean;
  pairing_active: boolean;
}

export interface PairingSession {
  session_id: string;
  address: string;
  device_name: string;
  stage: PairingStage;
  /** Nur für den Initiator; nach dem Ende null. */
  code: string | null;
  entered: number | null;
  /** Kuratierter Schlüssel: auth_failed | unreachable | timeout | unknown. */
  error: string | null;
}

function devicePath(address: string): string {
  return `${BASE}/devices/${encodeURIComponent(address)}`;
}

export async function getBluetoothState(): Promise<BluetoothState> {
  const { data } = await apiClient.get<BluetoothState>(`${BASE}/state`);
  return data;
}

export async function setAdapterPowered(powered: boolean): Promise<void> {
  await apiClient.post(`${BASE}/adapter/power`, { powered });
}

/** Startet das 30-s-Suchfenster; liefert dessen Ende als ISO-Zeit. */
export async function startScan(): Promise<string> {
  const { data } = await apiClient.post<{ until: string }>(`${BASE}/scan`);
  return data.until;
}

export async function connectDevice(address: string): Promise<void> {
  await apiClient.post(`${devicePath(address)}/connect`);
}

export async function disconnectDevice(address: string): Promise<void> {
  await apiClient.post(`${devicePath(address)}/disconnect`);
}

export async function removeDevice(address: string): Promise<void> {
  await apiClient.delete(devicePath(address));
}

/** Startet eine Kopplung; liefert die session_id. */
export async function startPairing(address: string): Promise<string> {
  const { data } = await apiClient.post<{ session_id: string }>(`${devicePath(address)}/pair`);
  return data.session_id;
}

/** Die eigene laufende Kopplung — oder null. */
export async function getPairingSession(): Promise<PairingSession | null> {
  const { data } = await apiClient.get<PairingSession | null>(`${BASE}/pairing`);
  return data;
}

export async function answerPairing(sessionId: string, accept: boolean): Promise<void> {
  await apiClient.post(`${BASE}/pairing/${encodeURIComponent(sessionId)}/confirm`, { accept });
}

export async function cancelPairing(sessionId: string): Promise<void> {
  await apiClient.post(`${BASE}/pairing/${encodeURIComponent(sessionId)}/cancel`);
}
