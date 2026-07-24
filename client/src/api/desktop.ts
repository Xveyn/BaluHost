/**
 * API client for Desktop (KDE/SDDM) toggle.
 *
 * Controls the display manager service so the GPU can enter a low-power
 * state while the NAS stays accessible. The desktop session is re-started
 * automatically when re-enabled.
 */

import { apiClient } from '../lib/api';

// ============================================================================
// Types
// ============================================================================

export type DesktopState = 'running' | 'stopped' | 'unknown';

export interface DesktopStatus {
  state: DesktopState;
  display_manager: string;
  detail: string | null;
}

export interface DesktopActionResult {
  success: boolean;
  message: string;
  session_unlocked?: boolean;
  unlock_message?: string;
}

// ============================================================================
// API functions
// ============================================================================

export async function getDesktopStatus(): Promise<DesktopStatus> {
  const { data } = await apiClient.get<DesktopStatus>('/api/system/sleep/desktop/status');
  return data;
}

export async function disableDesktop(): Promise<DesktopActionResult> {
  const { data } = await apiClient.post<DesktopActionResult>('/api/system/sleep/desktop/disable');
  return data;
}

export async function enableDesktop(): Promise<DesktopActionResult> {
  const { data } = await apiClient.post<DesktopActionResult>('/api/system/sleep/desktop/enable');
  return data;
}
