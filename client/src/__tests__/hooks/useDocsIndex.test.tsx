import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useDocsIndex } from '../../hooks/useDocsIndex';
import * as docsApi from '../../api/docs';
import type { DocsGroupInfo } from '../../api/docs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en-US' } }),
}));

vi.mock('../../api/docs');
const api = vi.mocked(docsApi);

const groups: DocsGroupInfo[] = [
  { id: 'g1', label: 'Getting started', icon: 'book', articles: [{ slug: 'intro', title: 'Intro', icon: 'file' }] },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDocsIndex', () => {
  it('loads the index for the current language', async () => {
    api.getDocsIndex.mockResolvedValue(groups);

    const { result } = renderHook(() => useDocsIndex(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.getDocsIndex).toHaveBeenCalledWith('en');
    expect(result.current.groups).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error string when the fetch fails', async () => {
    api.getDocsIndex.mockRejectedValue(new Error('docs index boom'));

    const { result } = renderHook(() => useDocsIndex(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.error).toBe('docs index boom'));
    expect(result.current.groups).toEqual([]);
  });
});
