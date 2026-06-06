import { apiClient } from '../lib/api';

export interface ActivityItem {
  id: number;
  user_id: number;
  username?: string | null;
  action_type: string;
  file_path: string;
  file_name: string;
  is_directory: boolean;
  file_size?: number | null;
  mime_type?: string | null;
  source: string;
  device_id?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityListResponse {
  activities: ActivityItem[];
  total: number;
  has_more: boolean;
}

export interface GetRecentActivitiesParams {
  limit?: number;
  offset?: number;
  scope?: 'mine' | 'all';
}

export async function getRecentActivities(
  params: GetRecentActivitiesParams = {},
): Promise<ActivityListResponse> {
  const { limit = 20, offset = 0, scope = 'mine' } = params;
  const { data } = await apiClient.get<ActivityListResponse>('/api/activity/recent', {
    params: { limit, offset, scope },
  });
  return data;
}
