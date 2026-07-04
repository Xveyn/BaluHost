import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useDocsArticle } from '../../hooks/useDocsArticle';
import * as docsApi from '../../api/docs';
import type { DocsArticle } from '../../api/docs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en-US' } }),
}));

vi.mock('../../api/docs');
const api = vi.mocked(docsApi);

const article: DocsArticle = {
  content: '# Hello',
  title: 'Hello',
  slug: 'hello',
  group: 'g1',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDocsArticle', () => {
  it('loads the article for a slug + language', async () => {
    api.getDocsArticle.mockResolvedValue(article);

    const { result } = renderHook(() => useDocsArticle('hello'), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.getDocsArticle).toHaveBeenCalledWith('hello', 'en');
    expect(result.current.article?.title).toBe('Hello');
    expect(result.current.error).toBeNull();
  });

  it('does not fetch when slug is null', () => {
    api.getDocsArticle.mockResolvedValue(article);

    const { result } = renderHook(() => useDocsArticle(null), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.article).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(api.getDocsArticle).not.toHaveBeenCalled();
  });

  it('surfaces an error string when the fetch fails', async () => {
    api.getDocsArticle.mockRejectedValue(new Error('article boom'));

    const { result } = renderHook(() => useDocsArticle('hello'), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('article boom'));
    expect(result.current.article).toBeNull();
  });
});
