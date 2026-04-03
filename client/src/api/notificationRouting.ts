/**
 * API client for user notification routing management.
 */

import { apiClient } from '../lib/api';

export interface UserNotificationRouting {
  user_id: number;
  receive_raid: boolean;
  receive_smart: boolean;
  receive_backup: boolean;
  receive_scheduler: boolean;
  receive_system: boolean;
  receive_security: boolean;
  receive_sync: boolean;
  receive_vpn: boolean;
  granted_by: number | null;
  granted_by_username: string | null;
  granted_at: string | null;
}

export interface UserNotificationRoutingUpdate {
  receive_raid?: boolean;
  receive_smart?: boolean;
  receive_backup?: boolean;
  receive_scheduler?: boolean;
  receive_system?: boolean;
  receive_security?: boolean;
  receive_sync?: boolean;
  receive_vpn?: boolean;
}

export interface MyNotificationRouting {
  receive_raid: boolean;
  receive_smart: boolean;
  receive_backup: boolean;
  receive_scheduler: boolean;
  receive_system: boolean;
  receive_security: boolean;
  receive_sync: boolean;
  receive_vpn: boolean;
}

/**
 * Get notification routing for a user (admin only).
 */
export async function getUserNotificationRouting(userId: number): Promise<UserNotificationRouting> {
  const { data } = await apiClient.get<UserNotificationRouting>(
    `/api/users/${userId}/notification-routing`,
  );
  return data;
}

/**
 * Update notification routing for a user (admin only).
 */
export async function updateUserNotificationRouting(
  userId: number,
  update: UserNotificationRoutingUpdate,
): Promise<UserNotificationRouting> {
  const { data } = await apiClient.put<UserNotificationRouting>(
    `/api/users/${userId}/notification-routing`,
    update,
  );
  return data;
}

/**
 * Get own notification routing (read-only).
 */
export async function getMyNotificationRouting(): Promise<MyNotificationRouting> {
  const { data } = await apiClient.get<MyNotificationRouting>(
    '/api/notifications/my-routing',
  );
  return data;
}
