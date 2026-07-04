/**
 * Docs (user manual) API client. The manual is language-scoped (lang param) and
 * public to authenticated users; reads are cached via TanStack Query in the
 * useDocsIndex / useDocsArticle hooks.
 */
import { apiClient } from '../lib/api';

export interface DocsArticleInfo {
  slug: string;
  title: string;
  icon: string;
}

export interface DocsGroupInfo {
  id: string;
  label: string;
  icon: string;
  articles: DocsArticleInfo[];
}

export interface DocsArticle {
  content: string;
  title: string;
  slug: string;
  group: string;
}

interface DocsIndexResponse {
  groups: DocsGroupInfo[];
}

export async function getDocsIndex(lang: string): Promise<DocsGroupInfo[]> {
  const { data } = await apiClient.get<DocsIndexResponse>('/api/docs/index', {
    params: { lang },
  });
  return data.groups;
}

export async function getDocsArticle(slug: string, lang: string): Promise<DocsArticle> {
  const { data } = await apiClient.get<DocsArticle>(`/api/docs/article/${slug}`, {
    params: { lang },
  });
  return data;
}
