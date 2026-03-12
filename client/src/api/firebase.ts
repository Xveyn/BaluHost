import { apiClient } from '../lib/api';

export interface FirebaseStatus {
  configured: boolean;
  initialized: boolean;
  project_id: string | null;
  client_email: string | null;
  credentials_source: 'file' | 'env_var' | null;
  file_exists: boolean;
  uploaded_at: string | null;
  sdk_installed: boolean;
}

export interface FirebaseUploadResponse {
  success: boolean;
  project_id: string | null;
  message: string;
}

export interface FirebaseDeleteResponse {
  success: boolean;
  message: string;
}

export async function getFirebaseStatus(): Promise<FirebaseStatus> {
  const { data } = await apiClient.get<FirebaseStatus>('/api/firebase/status');
  return data;
}

export async function uploadFirebaseCredentials(json: string): Promise<FirebaseUploadResponse> {
  const { data } = await apiClient.post<FirebaseUploadResponse>('/api/firebase/upload', {
    credentials_json: json,
  });
  return data;
}

export async function deleteFirebaseCredentials(): Promise<FirebaseDeleteResponse> {
  const { data } = await apiClient.delete<FirebaseDeleteResponse>('/api/firebase/credentials');
  return data;
}
