/**
 * API client for Pi-hole DNS integration.
 */

import { apiClient } from '../lib/api';

// ── Types ────────────────────────────────────────────────────────────

export interface PiholeStatus {
  mode: string;
  connected: boolean;
  blocking_enabled: boolean;
  version: string | null;
  container_running: boolean | null;
  container_status: string | null;
  uptime: number | null;
}

export interface PiholeSummary {
  total_queries: number;
  blocked_queries: number;
  percent_blocked: number;
  unique_domains: number;
  forwarded_queries: number;
  cached_queries: number;
  clients_seen: number;
  gravity_size: number;
  gravity_last_updated: string | null;
}

export interface BlockingState {
  blocking: string;
  timer: number | null;
}

export interface QueryEntry {
  timestamp: number;
  domain: string;
  client: string;
  query_type: string;
  status: string;
  reply_type: string;
  response_time: number;
}

export interface QueryLogResponse {
  queries: QueryEntry[];
  total: number;
}

export interface DomainEntry {
  domain: string;
  count: number;
}

export interface ClientEntry {
  client: string;
  name: string | null;
  count: number;
}

export interface HistoryEntry {
  timestamp: number;
  total: number;
  blocked: number;
}

export interface DomainListEntry {
  id: number | null;
  domain: string;
  comment: string;
  enabled: boolean;
  date_added: string | null;
  date_modified: string | null;
}

export interface AdlistEntry {
  id: number | null;
  url: string;
  comment: string;
  enabled: boolean;
  number: number;
  date_added: string | null;
  date_modified: string | null;
}

export interface LocalDnsEntry {
  domain: string;
  ip: string;
}

export interface ContainerActionResponse {
  success: boolean;
  message: string;
  container_status: string | null;
  password?: string;
}

export interface PiholeConfig {
  mode: string;
  pihole_url: string | null;
  upstream_dns: string;
  docker_image_tag: string;
  web_port: number;
  use_as_vpn_dns: boolean;
  remote_pihole_url: string | null;
  health_check_interval: number;
  failover_active: boolean;
  last_failover_at: string | null;
  has_password?: boolean;
  has_remote_password?: boolean;
  // DNS settings
  dns_dnssec: boolean;
  dns_rev_server: string | null;
  dns_rate_limit_count: number;
  dns_rate_limit_interval: number;
  dns_domain_needed: boolean;
  dns_bogus_priv: boolean;
  dns_domain_name: string;
  dns_expand_hosts: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface FailoverStatus {
  remote_configured: boolean;
  remote_connected: boolean;
  failover_active: boolean;
  active_source: 'remote' | 'local';
  remote_url: string | null;
  last_failover_at: string | null;
}

// ── API Functions ────────────────────────────────────────────────────

export async function getPiholeStatus(): Promise<PiholeStatus> {
  const { data } = await apiClient.get('/api/pihole/status');
  return data;
}

export async function getPiholeSummary(): Promise<PiholeSummary> {
  const { data } = await apiClient.get('/api/pihole/summary');
  return data;
}

export async function getBlocking(): Promise<BlockingState> {
  const { data } = await apiClient.get('/api/pihole/blocking');
  return data;
}

export async function setBlocking(enabled: boolean, timer?: number): Promise<BlockingState> {
  const { data } = await apiClient.post('/api/pihole/blocking', { enabled, timer });
  return data;
}

export async function getQueries(limit = 100, offset = 0): Promise<QueryLogResponse> {
  const { data } = await apiClient.get('/api/pihole/queries', { params: { limit, offset } });
  return data;
}

export async function getTopDomains(count = 10): Promise<{ top_permitted: DomainEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/top-domains', { params: { count } });
  return data;
}

export async function getTopBlocked(count = 10): Promise<{ top_blocked: DomainEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/top-blocked', { params: { count } });
  return data;
}

export async function getTopClients(count = 10): Promise<{ top_clients: ClientEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/top-clients', { params: { count } });
  return data;
}

export async function getHistory(): Promise<{ history: HistoryEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/history');
  return data;
}

export async function getDomains(listType: string, kind: string): Promise<{ domains: DomainListEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/domains', { params: { list_type: listType, kind } });
  return data;
}

export async function addDomain(listType: string, kind: string, domain: string, comment = ''): Promise<unknown> {
  const { data } = await apiClient.post('/api/pihole/domains', { list_type: listType, kind, domain, comment });
  return data;
}

export async function removeDomain(listType: string, kind: string, domain: string): Promise<unknown> {
  const { data } = await apiClient.delete('/api/pihole/domains', { data: { list_type: listType, kind, domain } });
  return data;
}

export async function getAdlists(): Promise<{ lists: AdlistEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/lists');
  return data;
}

export async function addAdlist(url: string, comment = ''): Promise<unknown> {
  const { data } = await apiClient.post('/api/pihole/lists', { url, comment });
  return data;
}

export async function removeAdlist(address: string): Promise<unknown> {
  const { data } = await apiClient.delete('/api/pihole/lists', { data: { address } });
  return data;
}

export async function toggleAdlist(address: string, enabled: boolean): Promise<unknown> {
  const { data } = await apiClient.patch('/api/pihole/lists/toggle', { address, enabled });
  return data;
}

export async function updateGravity(): Promise<unknown> {
  const { data } = await apiClient.post('/api/pihole/gravity');
  return data;
}

export async function getLocalDns(): Promise<{ records: LocalDnsEntry[] }> {
  const { data } = await apiClient.get('/api/pihole/dns-records');
  return data;
}

export async function addLocalDns(domain: string, ip: string): Promise<unknown> {
  const { data } = await apiClient.post('/api/pihole/dns-records', { domain, ip });
  return data;
}

export async function removeLocalDns(domain: string, ip: string): Promise<unknown> {
  const { data } = await apiClient.delete('/api/pihole/dns-records', { data: { domain, ip } });
  return data;
}

export async function restartDns(): Promise<unknown> {
  const { data } = await apiClient.post('/api/pihole/restart-dns');
  return data;
}

export async function deployContainer(config: {
  image_tag?: string;
  web_port?: number;
  upstream_dns?: string;
  timezone?: string;
}): Promise<ContainerActionResponse> {
  const { data } = await apiClient.post('/api/pihole/container/deploy', config);
  return data;
}

export async function startContainer(): Promise<ContainerActionResponse> {
  const { data } = await apiClient.post('/api/pihole/container/start');
  return data;
}

export async function stopContainer(): Promise<ContainerActionResponse> {
  const { data } = await apiClient.post('/api/pihole/container/stop');
  return data;
}

export async function removeContainer(): Promise<ContainerActionResponse> {
  const { data } = await apiClient.delete('/api/pihole/container');
  return data;
}

export async function updateContainer(): Promise<ContainerActionResponse> {
  const { data } = await apiClient.post('/api/pihole/container/update');
  return data;
}

export async function getContainerLogs(lines = 100): Promise<{ logs: string; lines: number }> {
  const { data } = await apiClient.get('/api/pihole/container/logs', { params: { lines } });
  return data;
}

export async function getPiholeConfig(): Promise<PiholeConfig> {
  const { data } = await apiClient.get('/api/pihole/config');
  return data;
}

export async function updatePiholeConfig(config: Partial<PiholeConfig & { password?: string; remote_password?: string }>): Promise<PiholeConfig> {
  const { data } = await apiClient.put('/api/pihole/config', config);
  return data;
}

export async function getFailoverStatus(): Promise<FailoverStatus> {
  const { data } = await apiClient.get('/api/pihole/failover-status');
  return data;
}

// ── Stored Queries (PostgreSQL Analytics) ───────────────────────────

export interface StoredQueryEntry {
  id: number;
  timestamp: string;
  domain: string;
  client: string;
  query_type: string;
  status: string;
  reply_type: string | null;
  response_time_ms: number | null;
}

export interface StoredQueryResponse {
  queries: StoredQueryEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface StoredStatsResponse {
  total_queries: number;
  blocked_queries: number;
  cached_queries: number;
  forwarded_queries: number;
  unique_domains: number;
  unique_clients: number;
  avg_response_time_ms: number | null;
  block_rate: number;
  period: string;
}

export interface StoredDomainEntry {
  domain: string;
  count: number;
}

export interface StoredClientEntry {
  client: string;
  count: number;
}

export interface HourlyCountEntry {
  hour: string;
  total_queries: number;
  blocked_queries: number;
  cached_queries: number;
  forwarded_queries: number;
}

export interface StoredHistoryResponse {
  history: HourlyCountEntry[];
  period: string;
}

export interface QueryCollectorStatus {
  running: boolean;
  is_enabled: boolean;
  last_poll_at: string | null;
  total_queries_stored: number;
  last_error: string | null;
  last_error_at: string | null;
  poll_interval_seconds: number;
  retention_days: number;
}

export type Period = '24h' | '7d' | '30d';

export async function getStoredQueries(params: {
  page?: number;
  page_size?: number;
  domain?: string;
  client?: string;
  status?: string;
  period?: Period;
}): Promise<StoredQueryResponse> {
  const { data } = await apiClient.get('/api/pihole/stored-queries', { params });
  return data;
}

export async function getStoredStats(period: Period = '24h'): Promise<StoredStatsResponse> {
  const { data } = await apiClient.get('/api/pihole/stored-stats', { params: { period } });
  return data;
}

export async function getStoredTopDomains(count = 10, period: Period = '24h'): Promise<{ top_domains: StoredDomainEntry[]; period: string }> {
  const { data } = await apiClient.get('/api/pihole/stored-top-domains', { params: { count, period } });
  return data;
}

export async function getStoredTopBlocked(count = 10, period: Period = '24h'): Promise<{ top_blocked: StoredDomainEntry[]; period: string }> {
  const { data } = await apiClient.get('/api/pihole/stored-top-blocked', { params: { count, period } });
  return data;
}

export async function getStoredTopClients(count = 10, period: Period = '24h'): Promise<{ top_clients: StoredClientEntry[]; period: string }> {
  const { data } = await apiClient.get('/api/pihole/stored-top-clients', { params: { count, period } });
  return data;
}

export async function getStoredHistory(period: Period = '24h'): Promise<StoredHistoryResponse> {
  const { data } = await apiClient.get('/api/pihole/stored-history', { params: { period } });
  return data;
}

export async function getCollectorStatus(): Promise<QueryCollectorStatus> {
  const { data } = await apiClient.get('/api/pihole/query-collector/status');
  return data;
}

export async function updateCollectorConfig(config: {
  is_enabled?: boolean;
  poll_interval_seconds?: number;
  retention_days?: number;
}): Promise<QueryCollectorStatus> {
  const { data } = await apiClient.put('/api/pihole/query-collector/config', config);
  return data;
}
