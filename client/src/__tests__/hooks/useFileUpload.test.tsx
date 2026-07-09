import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const { startUpload } = vi.hoisted(() => ({ startUpload: vi.fn() }));
vi.mock('../../contexts/UploadContext', () => ({
  useUpload: () => ({ startUpload, isUploading: false }),
}));

import { useFileUpload } from '../../hooks/useFileUpload';

const changeEvent = (files: unknown) =>
  ({ target: { files, value: 'keep' } } as unknown as React.ChangeEvent<HTMLInputElement>);
const dragEvent = (type: string) =>
  ({ type, preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as React.DragEvent);

beforeEach(() => vi.clearAllMocks());

describe('useFileUpload', () => {
  it('handleUpload forwards files, target path and availableBytes to startUpload and clears the input', () => {
    const getFullPath = () => '/mnt/main/docs';
    const { result } = renderHook(() => useFileUpload({ getFullPath, availableBytes: 123 }));
    const fakeList = { length: 1 } as unknown as FileList;
    const ev = changeEvent(fakeList);
    act(() => result.current.handleUpload(ev));
    expect(startUpload).toHaveBeenCalledWith(fakeList, '/mnt/main/docs', 123);
    expect((ev.target as HTMLInputElement).value).toBe('');
  });

  it('handleUpload is a no-op when no files are selected', () => {
    const { result } = renderHook(() => useFileUpload({ getFullPath: () => '/x' }));
    act(() => result.current.handleUpload(changeEvent(null)));
    expect(startUpload).not.toHaveBeenCalled();
  });

  it('handleDrag toggles dragActive on enter/leave', () => {
    const { result } = renderHook(() => useFileUpload({ getFullPath: () => '/x' }));
    act(() => result.current.handleDrag(dragEvent('dragenter')));
    expect(result.current.dragActive).toBe(true);
    act(() => result.current.handleDrag(dragEvent('dragleave')));
    expect(result.current.dragActive).toBe(false);
  });
});
