/**
 * API client for user power permissions management.
 */

import { apiClient } from '../lib/api';

export interface UserPowerPermissions {
  user_id: number;
  can_soft_sleep: boolean;
  can_wake: boolean;
  can_suspend: boolean;
  can_wol: boolean;
  granted_by: number | null;
  granted_by_username: string | null;
  granted_at: string | null;
}

export interface UserPowerPermissionsUpdate {
  can_soft_sleep?: boolean;
  can_wake?: boolean;
  can_suspend?: boolean;
  can_wol?: boolean;
}

export interface MyPowerPermissions {
  can_soft_sleep: boolean;
  can_wake: boolean;
  can_suspend: boolean;
  can_wol: boolean;
}

/**
 * Get power permissions for a user (admin only).
 */
export async function getUserPowerPermissions(userId: number): Promise<UserPowerPermissions> {
  const { data } = await apiClient.get<UserPowerPermissions>(
    `/api/users/${userId}/power-permissions`,
  );
  return data;
}

/**
 * Update power permissions for a user (admin only).
 */
export async function updateUserPowerPermissions(
  userId: number,
  update: UserPowerPermissionsUpdate,
): Promise<UserPowerPermissions> {
  const { data } = await apiClient.put<UserPowerPermissions>(
    `/api/users/${userId}/power-permissions`,
    update,
  );
  return data;
}

/**
 * Get own power permissions (for mobile app / client apps).
 */
export async function getMyPowerPermissions(): Promise<MyPowerPermissions> {
  const { data } = await apiClient.get<MyPowerPermissions>(
    '/api/system/sleep/my-permissions',
  );
  return data;
}
