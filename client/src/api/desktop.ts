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
  /**
   * Whether the graphical session is locked. `null` means the server could not
   * tell (no session, no loginctl) — never treat that as "unlocked".
   */
  session_locked?: boolean | null;
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

/**
 * Unlock the KDE session without touching the displays.
 *
 * `enableDesktop()` unlocks as a side effect of turning the screens on; this is
 * the same action for when they are already on. A refusal (wrong network, no
 * permission) comes back as `success: false`, not as an HTTP error.
 */
export async function unlockSession(): Promise<DesktopActionResult> {
  const { data } = await apiClient.post<DesktopActionResult>('/api/system/sleep/desktop/unlock');
  return data;
}
