import { apiClient } from '../lib/api';
import type { User } from '../types/auth';

export interface ImpersonationResponse {
  access_token: string;
  token_type: 'bearer';
  user: User;
}

export async function impersonateUser(userId: number): Promise<ImpersonationResponse> {
  const { data } = await apiClient.post<ImpersonationResponse>(
    `/api/auth/dev/impersonate/${userId}`,
  );
  return data;
}
