import { useCallback, useState } from 'react';
import type React from 'react';
import { useUpload } from '../contexts/UploadContext';

export interface UseFileUploadResult {
  dragActive: boolean;
  isUploading: boolean;
  handleUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleFolderUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleDrag: (e: React.DragEvent) => void;
  handleDrop: (e: React.DragEvent) => Promise<void>;
}

async function traverseFileTree(item: FileSystemEntry, path = ''): Promise<File[]> {
  const files: File[] = [];
  if (item.isFile) {
    return new Promise((resolve) => {
      (item as FileSystemFileEntry).file((file: File) => {
        const newFile = new File([file], path + file.name, { type: file.type });
        Object.defineProperty(newFile, 'webkitRelativePath', { value: path + file.name, writable: false });
        resolve([newFile]);
      });
    });
  } else if (item.isDirectory) {
    const dirReader = (item as FileSystemDirectoryEntry).createReader();
    return new Promise((resolve) => {
      const readEntries = () => {
        dirReader.readEntries(async (entries: FileSystemEntry[]) => {
          if (entries.length === 0) {
            resolve(files);
          } else {
            for (const entry of entries) {
              const subFiles = await traverseFileTree(entry, path + item.name + '/');
              files.push(...subFiles);
            }
            readEntries();
          }
        });
      };
      readEntries();
    });
  }
  return files;
}

export function useFileUpload(opts: { getFullPath: () => string; availableBytes?: number | null }): UseFileUploadResult {
  const { getFullPath, availableBytes } = opts;
  const { startUpload, isUploading } = useUpload();
  const [dragActive, setDragActive] = useState(false);

  const handleUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) return;
      startUpload(fileList, getFullPath(), availableBytes);
      e.target.value = '';
    },
    [startUpload, getFullPath, availableBytes],
  );

  const handleFolderUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) return;
      startUpload(fileList, getFullPath(), availableBytes);
      e.target.value = '';
    },
    [startUpload, getFullPath, availableBytes],
  );

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      const items = e.dataTransfer.items;
      if (!items) return;
      const allFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i].webkitGetAsEntry();
        if (item) {
          const dropped = await traverseFileTree(item);
          allFiles.push(...dropped);
        }
      }
      if (allFiles.length > 0) {
        const dt = new DataTransfer();
        allFiles.forEach((file) => dt.items.add(file));
        startUpload(dt.files, getFullPath(), availableBytes);
      }
    },
    [startUpload, getFullPath, availableBytes],
  );

  return { dragActive, isUploading, handleUpload, handleFolderUpload, handleDrag, handleDrop };
}
