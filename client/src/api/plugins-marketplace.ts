/**
 * Plugin Marketplace API client.
 *
 * Wraps the `/api/plugins/marketplace/*` admin-only routes that list
 * upstream plugins and install/uninstall them on disk.
 */
import { apiClient } from '../lib/api';

export interface MarketplaceVersion {
  version: string;
  min_baluhost_version?: string | null;
  max_baluhost_version?: string | null;
  python_requirements: string[];
  required_permissions: string[];
  download_url: string;
  checksum_sha256: string;
  size_bytes: number;
  released_at?: string | null;
}

export interface MarketplacePlugin {
  name: string;
  latest_version: string;
  display_name: string;
  description: string;
  author: string;
  homepage?: string | null;
  category: string;
  versions: MarketplaceVersion[];
}

export interface MarketplaceIndex {
  index_version: number;
  generated_at?: string | null;
  plugins: MarketplacePlugin[];
}

export interface MarketplaceConflict {
  package: string;
  requirement: string;
  found?: string | null;
  source: string;
  suggestion: string;
}

export interface MarketplaceInstallRequest {
  version?: string;
  force?: boolean;
}

export interface MarketplaceInstallResponse {
  name: string;
  version: string;
  installed_path: string;
  shared_satisfied: string[];
  isolated_installed: string[];
}

/** Backend 409 body shape for resolver conflicts. */
export interface MarketplaceConflictDetail {
  error: 'resolver_conflict';
  conflicts: MarketplaceConflict[];
}

export async function listMarketplace(
  refresh: boolean = false,
): Promise<MarketplaceIndex> {
  const response = await apiClient.get<MarketplaceIndex>(
    '/api/plugins/marketplace',
    { params: refresh ? { refresh: true } : undefined },
  );
  return response.data;
}

export async function installMarketplacePlugin(
  name: string,
  payload: MarketplaceInstallRequest = {},
): Promise<MarketplaceInstallResponse> {
  const response = await apiClient.post<MarketplaceInstallResponse>(
    `/api/plugins/marketplace/${encodeURIComponent(name)}/install`,
    payload,
  );
  return response.data;
}

export async function uninstallMarketplacePlugin(name: string): Promise<void> {
  await apiClient.delete(
    `/api/plugins/marketplace/${encodeURIComponent(name)}`,
  );
}
