/**
 * API client for Ad Discovery feature.
 */
import { apiClient } from '../lib/api';

// ── Types ────────────────────────────────────────────────────────

export interface SuspectEntry {
  id: number;
  domain: string;
  first_seen_at: string;
  last_seen_at: string;
  query_count: number;
  heuristic_score: number;
  matched_patterns: string[] | null;
  community_hits: number;
  community_lists: string[] | null;
  source: string;
  status: string;
  resolved_at: string | null;
}

export interface PatternEntry {
  id: number;
  pattern: string;
  is_regex: boolean;
  weight: number;
  category: string;
  is_default: boolean;
  enabled: boolean;
}

export interface ReferenceListEntry {
  id: number;
  name: string;
  url: string;
  is_default: boolean;
  enabled: boolean;
  domain_count: number;
  last_fetched_at: string | null;
  fetch_interval_hours: number;
  last_error: string | null;
}

export interface CustomListEntry {
  id: number;
  name: string;
  description: string;
  domain_count: number;
  created_at: string;
  updated_at: string;
  deployed: boolean;
  adlist_url: string | null;
}

export interface CustomListDomainEntry {
  id: number;
  domain: string;
  added_at: string;
  comment: string;
}

export interface AdDiscoveryStatus {
  suspects_new: number;
  suspects_confirmed: number;
  suspects_dismissed: number;
  suspects_blocked: number;
  last_analysis_at: string | null;
  background_task_running: boolean;
  reference_lists_active: number;
  reference_lists_total: number;
  custom_lists_total: number;
  custom_lists_deployed: number;
}

export interface AdDiscoveryConfig {
  background_interval_hours: number;
  heuristic_weight: number;
  community_weight: number;
  min_score: number;
  re_evaluation_threshold: number;
  background_enabled: boolean;
}

// ── API Functions ────────────────────────────────────────────────

const BASE = '/api/pihole/ad-discovery';

// Status & Config
export async function getAdDiscoveryStatus(): Promise<AdDiscoveryStatus> {
  const { data } = await apiClient.get(`${BASE}/status`);
  return data;
}

export async function getAdDiscoveryConfig(): Promise<AdDiscoveryConfig> {
  const { data } = await apiClient.get(`${BASE}/config`);
  return data;
}

export async function updateAdDiscoveryConfig(update: Partial<AdDiscoveryConfig>): Promise<AdDiscoveryConfig> {
  const { data } = await apiClient.patch(`${BASE}/config`, update);
  return data;
}

// Analysis
export async function startAnalysis(period = '24h', minScore = 0.15) {
  const { data } = await apiClient.post(`${BASE}/analyze`, { period, min_score: minScore });
  return data;
}

// Suspects
export async function getSuspects(params: {
  status?: string; source?: string; sort_by?: string;
  page?: number; page_size?: number;
}) {
  const { data } = await apiClient.get(`${BASE}/suspects`, { params });
  return data as { suspects: SuspectEntry[]; total: number; page: number; page_size: number };
}

export async function updateSuspectStatus(domain: string, status: string) {
  const { data } = await apiClient.patch(`${BASE}/suspects/${encodeURIComponent(domain)}`, { status });
  return data;
}

export async function addManualSuspect(domain: string) {
  const { data } = await apiClient.post(`${BASE}/suspects/manual`, { domain });
  return data;
}

export async function blockSuspect(domain: string, target: string, listId?: number) {
  const { data } = await apiClient.post(`${BASE}/suspects/block`, {
    domain, target, list_id: listId,
  });
  return data;
}

export async function bulkAction(domains: string[], action: string, target?: string, listId?: number) {
  const { data } = await apiClient.post(`${BASE}/suspects/bulk-action`, {
    domains, action, target, list_id: listId,
  });
  return data;
}

// Patterns
export async function getPatterns() {
  const { data } = await apiClient.get(`${BASE}/patterns`);
  return data as { patterns: PatternEntry[] };
}

export async function createPattern(pattern: { pattern: string; is_regex: boolean; weight: number; category: string }) {
  const { data } = await apiClient.post(`${BASE}/patterns`, pattern);
  return data;
}

export async function updatePattern(id: number, update: { weight?: number; enabled?: boolean; category?: string }) {
  const { data } = await apiClient.patch(`${BASE}/patterns/${id}`, update);
  return data;
}

export async function deletePattern(id: number) {
  const { data } = await apiClient.delete(`${BASE}/patterns/${id}`);
  return data;
}

// Reference Lists
export async function getReferenceLists() {
  const { data } = await apiClient.get(`${BASE}/reference-lists`);
  return data as { lists: ReferenceListEntry[] };
}

export async function createReferenceList(list: { name: string; url: string; fetch_interval_hours?: number }) {
  const { data } = await apiClient.post(`${BASE}/reference-lists`, list);
  return data;
}

export async function updateReferenceList(id: number, update: { enabled?: boolean; fetch_interval_hours?: number }) {
  const { data } = await apiClient.patch(`${BASE}/reference-lists/${id}`, update);
  return data;
}

export async function deleteReferenceList(id: number) {
  const { data } = await apiClient.delete(`${BASE}/reference-lists/${id}`);
  return data;
}

export async function refreshReferenceLists() {
  const { data } = await apiClient.post(`${BASE}/reference-lists/refresh`);
  return data;
}

// Custom Lists
export async function getCustomLists() {
  const { data } = await apiClient.get(`${BASE}/custom-lists`);
  return data as { lists: CustomListEntry[] };
}

export async function createCustomList(list: { name: string; description?: string }) {
  const { data } = await apiClient.post(`${BASE}/custom-lists`, list);
  return data;
}

export async function updateCustomList(id: number, update: { name?: string; description?: string }) {
  const { data } = await apiClient.patch(`${BASE}/custom-lists/${id}`, update);
  return data;
}

export async function deleteCustomList(id: number) {
  const { data } = await apiClient.delete(`${BASE}/custom-lists/${id}`);
  return data;
}

export async function getCustomListDomains(id: number, page = 1, pageSize = 100) {
  const { data } = await apiClient.get(`${BASE}/custom-lists/${id}/domains`, {
    params: { page, page_size: pageSize },
  });
  return data as { domains: CustomListDomainEntry[]; total: number };
}

export async function addCustomListDomains(id: number, domains: string[], comment = '') {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/domains`, { domains, comment });
  return data;
}

export async function removeCustomListDomain(id: number, domain: string) {
  const { data } = await apiClient.delete(`${BASE}/custom-lists/${id}/domains/${encodeURIComponent(domain)}`);
  return data;
}

export async function deployCustomList(id: number) {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/deploy`);
  return data;
}

export async function undeployCustomList(id: number) {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/undeploy`);
  return data;
}

export async function exportCustomList(id: number): Promise<Blob> {
  const { data } = await apiClient.get(`${BASE}/custom-lists/${id}/export`, {
    responseType: 'blob',
  });
  return data;
}
