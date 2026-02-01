/**
 * Plugin API client for BaluHost Plugin Management
 */
import { apiClient } from '../lib/api';

// Types
export interface PluginNavItem {
  path: string;
  label: string;
  icon: string;
  admin_only: boolean;
  order: number;
}

export interface PluginInfo {
  name: string;
  version: string;
  display_name: string;
  description: string;
  author: string;
  category: string;
  required_permissions: string[];
  dangerous_permissions: string[];
  is_enabled: boolean;
  has_ui: boolean;
  has_routes: boolean;
  error?: string;
}

export interface PluginListResponse {
  plugins: PluginInfo[];
  total: number;
}

export interface PluginUIInfo {
  name: string;
  display_name: string;
  nav_items: PluginNavItem[];
  bundle_path: string;
  styles_path?: string;
  dashboard_widgets: string[];
}

export interface PluginUIManifest {
  plugins: PluginUIInfo[];
}

export interface PluginDetail {
  name: string;
  version: string;
  display_name: string;
  description: string;
  author: string;
  category: string;
  homepage?: string;
  min_baluhost_version?: string;
  dependencies: string[];
  required_permissions: string[];
  granted_permissions: string[];
  dangerous_permissions: string[];
  is_enabled: boolean;
  is_installed: boolean;
  has_ui: boolean;
  has_routes: boolean;
  has_background_tasks: boolean;
  nav_items: PluginNavItem[];
  dashboard_widgets: string[];
  installed_at?: string;
  enabled_at?: string;
  config: Record<string, unknown>;
  config_schema?: Record<string, unknown>;
}

export interface PluginToggleRequest {
  enabled: boolean;
  grant_permissions?: string[];
}

export interface PluginToggleResponse {
  name: string;
  is_enabled: boolean;
  message: string;
}

export interface PluginConfigResponse {
  name: string;
  config: Record<string, unknown>;
  schema?: Record<string, unknown>;
}

export interface PermissionInfo {
  name: string;
  value: string;
  dangerous: boolean;
  description: string;
}

export interface PermissionListResponse {
  permissions: PermissionInfo[];
}

/**
 * List all available plugins
 */
export async function listPlugins(): Promise<PluginListResponse> {
  const response = await apiClient.get<PluginListResponse>('/api/plugins');
  return response.data;
}

/**
 * Get plugin details
 */
export async function getPluginDetails(name: string): Promise<PluginDetail> {
  const response = await apiClient.get<PluginDetail>(`/api/plugins/${name}`);
  return response.data;
}

/**
 * Toggle plugin enabled state
 */
export async function togglePlugin(
  name: string,
  request: PluginToggleRequest
): Promise<PluginToggleResponse> {
  const response = await apiClient.post<PluginToggleResponse>(
    `/api/plugins/${name}/toggle`,
    request
  );
  return response.data;
}

/**
 * Get plugin configuration
 */
export async function getPluginConfig(name: string): Promise<PluginConfigResponse> {
  const response = await apiClient.get<PluginConfigResponse>(`/api/plugins/${name}/config`);
  return response.data;
}

/**
 * Update plugin configuration
 */
export async function updatePluginConfig(
  name: string,
  config: Record<string, unknown>
): Promise<PluginConfigResponse> {
  const response = await apiClient.put<PluginConfigResponse>(
    `/api/plugins/${name}/config`,
    { config }
  );
  return response.data;
}

/**
 * Get UI manifest for all enabled plugins
 */
export async function getUIManifest(): Promise<PluginUIManifest> {
  const response = await apiClient.get<PluginUIManifest>('/api/plugins/ui/manifest');
  return response.data;
}

/**
 * List all available permissions
 */
export async function listPermissions(): Promise<PermissionListResponse> {
  const response = await apiClient.get<PermissionListResponse>('/api/plugins/permissions');
  return response.data;
}

/**
 * Uninstall a plugin
 */
export async function uninstallPlugin(name: string): Promise<{ message: string }> {
  const response = await apiClient.delete<{ message: string }>(`/api/plugins/${name}`);
  return response.data;
}

/**
 * Get plugin UI bundle URL
 */
export function getPluginBundleUrl(pluginName: string, bundlePath: string): string {
  return `/api/plugins/${pluginName}/ui/${bundlePath}`;
}
