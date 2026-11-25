/**
 * API-Client des Plugins `local_tls` (Zertifikat und DNS fuer das LAN).
 *
 * Alle Routen sind Admin-only. Der Anbieter-Token ist schreibend-only: er
 * kommt in keiner Antwort zurueck, `token_set` sagt nur, ob einer vorliegt.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/local_tls';

export type LegoState = 'ok' | 'missing' | 'too_old';

export interface LocalTlsStatus {
  configured: boolean;
  lego: LegoState;
  lego_version: string | null;
  current_ip: string | null;
  last_ip: string | null;
  last_ip_set_at: string | null;
  cert_not_after: string | null;
  cert_fingerprint: string | null;
  served_matches: boolean | null;
  last_renew_at: string | null;
  last_renew_ok: boolean | null;
  last_renew_reason: string | null;
  running: boolean;
  token_set: boolean;
  nginx_hint: string | null;
}

export async function getLocalTlsStatus(): Promise<LocalTlsStatus> {
  const res = await apiClient.get<LocalTlsStatus>(`${BASE}/status`);
  return res.data;
}

export async function setLocalTlsToken(token: string): Promise<void> {
  await apiClient.put(`${BASE}/credentials`, { token });
}

export async function clearLocalTlsToken(): Promise<void> {
  await apiClient.delete(`${BASE}/credentials`);
}

export async function renewLocalTls(): Promise<LocalTlsStatus> {
  const res = await apiClient.post<LocalTlsStatus>(`${BASE}/renew`);
  return res.data;
}

export async function updateLocalTlsDns(): Promise<LocalTlsStatus> {
  const res = await apiClient.post<LocalTlsStatus>(`${BASE}/update-dns`);
  return res.data;
}

/** Fehlerschluessel aus `{"error": ...}` oder `{"detail": {"error": ...}}`. */
export function localTlsErrorKey(err: unknown): string | null {
  const data = (err as { response?: { data?: any } })?.response?.data;
  return data?.error ?? data?.detail?.error ?? null;
}
