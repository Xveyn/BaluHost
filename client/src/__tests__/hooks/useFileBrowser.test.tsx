import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }) }));
vi.mock('../../api/files', () => ({
  getMountpoints: vi.fn(),
  listFiles: vi.fn(),
  createFolder: vi.fn(),
  deleteFile: vi.fn(),
  renameFile: vi.fn(),
  downloadFileBlob: vi.fn(),
}));

import * as filesApi from '../../api/files';
import { useFileBrowser } from '../../hooks/useFileBrowser';

const mp = { id: 'a', name: 'Main', type: 'raid', path: '/mnt/main', size_bytes: 100, used_bytes: 40, available_bytes: 60, status: 'ok', is_default: true };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(filesApi.getMountpoints).mockResolvedValue({ mountpoints: [mp] } as never);
  vi.mocked(filesApi.listFiles).mockResolvedValue({ files: [{ name: 'a.txt', path: 'a.txt', size: 1, type: 'file', modified_at: '2026-01-01T00:00:00Z' }] } as never);
  vi.mocked(filesApi.createFolder).mockResolvedValue({} as never);
  vi.mocked(filesApi.deleteFile).mockResolvedValue({} as never);
  vi.mocked(filesApi.renameFile).mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe('useFileBrowser', () => {
  it('auto-selects the default mountpoint and lists its root', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    expect(result.current.currentPath).toBe('');
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    expect(filesApi.listFiles).toHaveBeenCalledWith('/mnt/main');
    expect(result.current.files[0].name).toBe('a.txt');
    expect(result.current.storageInfo).toEqual({ totalBytes: 100, usedBytes: 40, availableBytes: 60 });
  });

  it('does not list before a mountpoint is selected', async () => {
    vi.mocked(filesApi.getMountpoints).mockResolvedValue({ mountpoints: [] } as never);
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    // Wait until mountpoints have actually resolved (empty) — proves the empty
    // result does not select a mountpoint and therefore never lists.
    await waitFor(() => expect(filesApi.getMountpoints).toHaveBeenCalled());
    await act(async () => { await Promise.resolve(); });
    expect(result.current.selectedMountpoint).toBeNull();
    expect(filesApi.listFiles).not.toHaveBeenCalled();
  });

  it('navigateToFolder re-lists the new full path', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    act(() => result.current.navigateToFolder('/mnt/main/docs'));
    await waitFor(() => expect(result.current.currentPath).toBe('docs'));
    await waitFor(() => expect(filesApi.listFiles).toHaveBeenCalledWith('/mnt/main/docs'));
  });

  it('createFolder posts and invalidates the listing', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    expect(filesApi.listFiles).toHaveBeenCalledTimes(1);
    let ok = false;
    await act(async () => { ok = await result.current.createFolder('New'); });
    expect(ok).toBe(true);
    expect(filesApi.createFolder).toHaveBeenCalledWith({ path: '/mnt/main', name: 'New' });
    await waitFor(() => expect(filesApi.listFiles).toHaveBeenCalledTimes(2));
  });

  it('createFolder rejects an empty name without calling the API', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.selectedMountpoint?.id).toBe('a'));
    let ok = true;
    await act(async () => { ok = await result.current.createFolder('   '); });
    expect(ok).toBe(false);
    expect(filesApi.createFolder).not.toHaveBeenCalled();
  });

  it('deleteFile and renameFile call the API with the file path', async () => {
    const { result } = renderHook(() => useFileBrowser(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    await act(async () => { await result.current.deleteFile(result.current.files[0]); });
    expect(filesApi.deleteFile).toHaveBeenCalledWith('a.txt');
    await act(async () => { await result.current.renameFile(result.current.files[0], 'b.txt'); });
    expect(filesApi.renameFile).toHaveBeenCalledWith({ old_path: 'a.txt', new_name: 'b.txt' });
  });
});
