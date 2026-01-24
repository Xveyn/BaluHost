/**
 * Local FastAPI Backend Client
 * 
 * Direct HTTP client for communicating with the Python FastAPI backend
 * when running on localhost. Provides JWT authentication and automatic
 * token management with fallback to IPC.
 */

import { getToken, storeToken, clearToken } from './secureStore';

const LOCAL_API_BASE = 'http://127.0.0.1:3001';
const API_PREFIX = '/api';

export interface LocalApiConfig {
  baseUrl?: string;
  timeout?: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username: string;
    role: string;
    email?: string;
  };
}

export interface ServerProfile {
  id: number;
  name: string;
  ssh_host: string;
  ssh_port: number;
  ssh_username: string;
  vpn_profile_id?: number;
  power_on_command?: string;
  last_used?: string;
  created_at: string;
  updated_at?: string;
  user_id?: number;
  owner?: string;
}

export interface CreateProfileRequest {
  name: string;
  ssh_host: string;
  ssh_port: number;
  ssh_username: string;
  ssh_private_key: string;
  vpn_profile_id?: number;
  power_on_command?: string;
}

export class LocalApiError extends Error {
  statusCode?: number;
  detail?: string;

  constructor(
    message: string,
    statusCode?: number,
    detail?: string
  ) {
    super(message);
    this.name = 'LocalApiError';
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export class LocalApi {
  private baseUrl: string;
  private timeout: number;

  constructor(config: LocalApiConfig = {}) {
    this.baseUrl = config.baseUrl || LOCAL_API_BASE;
    this.timeout = config.timeout || 5000;
  }

  /**
   * Check if local backend is available
   */
  async isAvailable(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);

      const response = await fetch(`${this.baseUrl}/api/health`, {
        method: 'GET',
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      console.debug('[LocalApi] Backend not available:', error);
      return false;
    }
  }

  /**
   * Make authenticated request with automatic token handling
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = await getToken();
    const url = `${this.baseUrl}${API_PREFIX}${endpoint}`;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Handle 401 - token expired or invalid
      if (response.status === 401) {
        console.warn('[LocalApi] Token expired or invalid, clearing token');
        await clearToken();
        throw new LocalApiError('Authentication expired', 401, 'Token invalid or expired');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new LocalApiError(
          errorData.detail || `HTTP ${response.status}`,
          response.status,
          errorData.detail
        );
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof LocalApiError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new LocalApiError('Request timeout', 408, 'Request took too long');
        }
        throw new LocalApiError(`Network error: ${error.message}`, 0, error.message);
      }

      throw new LocalApiError('Unknown error occurred', 0);
    }
  }

  /**
   * Login with username and password
   */
  async login(username: string, password: string): Promise<LoginResponse> {
    try {
      const response = await this.request<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });

      // Store token securely
      await storeToken(response.access_token, username);
      console.log('[LocalApi] Login successful, token stored');

      return response;
    } catch (error) {
      console.error('[LocalApi] Login failed:', error);
      throw error;
    }
  }

  /**
   * Get current authenticated user
   */
  async getCurrentUser() {
    return this.request('/auth/me', { method: 'GET' });
  }

  /**
   * Get server profiles for current user (authenticated)
   */
  async getServerProfiles(): Promise<ServerProfile[]> {
    return this.request<ServerProfile[]>('/server-profiles', { method: 'GET' });
  }

  /**
   * Get all server profiles (unauthenticated - for login screen)
   */
  async getPublicServerProfiles(): Promise<ServerProfile[]> {
    const url = `${this.baseUrl}${API_PREFIX}/server-profiles/public`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new LocalApiError(`HTTP ${response.status}`, response.status);
      }

      return await response.json();
    } catch (error) {
      console.error('[LocalApi] Failed to fetch public profiles:', error);
      throw error;
    }
  }

  /**
   * Create new server profile
   */
  async createServerProfile(profile: CreateProfileRequest): Promise<ServerProfile> {
    return this.request<ServerProfile>('/server-profiles', {
      method: 'POST',
      body: JSON.stringify(profile),
    });
  }

  /**
   * Update server profile
   */
  async updateServerProfile(id: number, profile: Partial<CreateProfileRequest>): Promise<ServerProfile> {
    return this.request<ServerProfile>(`/server-profiles/${id}`, {
      method: 'PUT',
      body: JSON.stringify(profile),
    });
  }

  /**
   * Delete server profile
   */
  async deleteServerProfile(id: number): Promise<void> {
    return this.request<void>(`/server-profiles/${id}`, {
      method: 'DELETE',
    });
  }

  /**
   * Logout (clear token)
   */
  async logout(): Promise<void> {
    await clearToken();
    console.log('[LocalApi] Logged out, token cleared');
  }

  /**
   * Request a backend shutdown (admin only).
   */
  async shutdown(): Promise<{ message?: string; initiated_by?: string; eta_seconds?: number }> {
    // Get token from localStorage (where App.tsx stores it)
    const token = localStorage.getItem('token');

    if (!token) {
      throw new LocalApiError('No authentication token found', 401);
    }

    try {
      return await this.request('/system/shutdown', { method: 'POST' });
    } catch (err) {
      // Fallback for dev setup where backend runs on same origin (uvicorn on :8000)
      // or when the local HTTP proxy is not available. Attempt a same-origin call.
      try {
        const res = await fetch(`${API_PREFIX}/system/shutdown`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new LocalApiError(errData.detail || `HTTP ${res.status}`, res.status);
        }
        return await res.json();
      } catch (err2) {
        throw err2;
      }
    }
  }
}

// Singleton instance
export const localApi = new LocalApi();

/**
 * Helper: Check if local backend is available
 */
export async function isLocalBackendAvailable(): Promise<boolean> {
  return localApi.isAvailable();
}

/**
 * Helper: Login with automatic local detection
 */
export async function loginLocal(username: string, password: string): Promise<LoginResponse> {
  return localApi.login(username, password);
}

/**
 * Helper: Get profiles with automatic fallback
 */
export async function getProfilesWithFallback(): Promise<ServerProfile[]> {
  try {
    // Try local API first
    if (await localApi.isAvailable()) {
      return await localApi.getServerProfiles();
    }
  } catch (error) {
    console.warn('[LocalApi] Failed, falling back to IPC:', error);
  }

  // Fallback to IPC (via BaluDesk electronAPI)
  if (window.electronAPI && window.electronAPI.sendIPCMessage) {
    const result = await window.electronAPI.sendIPCMessage({
      type: 'get_remote_server_profiles'
    });
    return result.data?.profiles || [];
  }

  throw new Error('No backend available (local or IPC)');
}
