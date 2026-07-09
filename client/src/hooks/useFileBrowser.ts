import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import {
  getMountpoints,
  listFiles,
  createFolder as apiCreateFolder,
  deleteFile as apiDeleteFile,
  renameFile as apiRenameFile,
  downloadFileBlob,
} from '../api/files';
import { getFullPath, mapApiFileItem, parentPath, toRelativePath } from '../components/file-manager/utils';
import type { FileItem, StorageInfo, StorageMountpoint } from '../components/file-manager/types';

// Stable empty-array references. IMPORTANT: the page has effects keyed on `files`
// (e.g. the owner-name cache in FileManager.tsx). Returning a fresh `[]` on every
// render while the query has no data yet would re-fire those effects every render
// (setUserCache → re-render → new [] → …), an infinite loop. Keep these stable.
const EMPTY_FILES: FileItem[] = [];
const EMPTY_MOUNTPOINTS: StorageMountpoint[] = [];

const getErrorMessage = (error: unknown): string => {
  if (!error || typeof error !== 'object') return 'Unknown error';
  const obj = error as Record<string, unknown>;
  return String(obj.error ?? obj.detail ?? 'Unknown error');
};
const errDetail = (err: unknown) => (err as { response?: { data?: unknown } })?.response?.data ?? err;

export interface UseFileBrowserResult {
  mountpoints: StorageMountpoint[];
  selectedMountpoint: StorageMountpoint | null;
  selectMountpoint: (mp: StorageMountpoint) => void;
  currentPath: string;
  getFullPath: (path?: string) => string;
  navigateToFolder: (folderPath: string) => void;
  goBack: () => void;
  goHome: () => void;
  files: FileItem[];
  loading: boolean;
  storageInfo: StorageInfo | null;
  createFolder: (name: string) => Promise<boolean>;
  deleteFile: (file: FileItem) => Promise<boolean>;
  renameFile: (file: FileItem, newName: string) => Promise<boolean>;
  downloadFile: (file: FileItem) => Promise<void>;
  refresh: () => void;
}

export function useFileBrowser(): UseFileBrowserResult {
  const { t } = useTranslation(['fileManager', 'common']);
  const queryClient = useQueryClient();
  const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
  const [currentPath, setCurrentPath] = useState('');

  const mountpointsQuery = useQuery({ queryKey: queryKeys.files.mountpoints(), queryFn: getMountpoints });

  // Auto-select the default mountpoint once loaded (matches the old loadMountpoints()).
  useEffect(() => {
    if (selectedMountpoint || !mountpointsQuery.data) return;
    const mps = mountpointsQuery.data.mountpoints;
    const def = mps.find((mp) => mp.is_default) ?? mps[0];
    if (def) {
      setSelectedMountpoint(def);
      setCurrentPath('');
    }
  }, [mountpointsQuery.data, selectedMountpoint]);

  // Preserve the original toast on a mountpoints load failure.
  useEffect(() => {
    if (mountpointsQuery.isError) toast.error('Failed to load storage devices');
  }, [mountpointsQuery.isError]);

  const resolveFullPath = useCallback(
    (path: string = currentPath) => getFullPath(selectedMountpoint, path),
    [selectedMountpoint, currentPath],
  );
  const fullPath = resolveFullPath();

  const filesQuery = useQuery({
    queryKey: queryKeys.files.list(fullPath),
    queryFn: async () => {
      const data = await listFiles(fullPath);
      return Array.isArray(data.files) ? data.files.map(mapApiFileItem) : [];
    },
    enabled: !!selectedMountpoint,
  });

  const files = filesQuery.data ?? EMPTY_FILES;
  const loading = filesQuery.isFetching;

  const storageInfo: StorageInfo | null = selectedMountpoint
    ? {
        totalBytes: selectedMountpoint.size_bytes,
        usedBytes: selectedMountpoint.used_bytes,
        availableBytes: selectedMountpoint.available_bytes,
      }
    : null;

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.files.list(fullPath) });
  }, [queryClient, fullPath]);

  const selectMountpoint = useCallback((mp: StorageMountpoint) => {
    setSelectedMountpoint(mp);
    setCurrentPath('');
  }, []);

  const navigateToFolder = useCallback(
    (folderPath: string) => setCurrentPath(toRelativePath(selectedMountpoint, folderPath)),
    [selectedMountpoint],
  );
  const goBack = useCallback(() => setCurrentPath((p) => parentPath(p)), []);
  const goHome = useCallback(() => setCurrentPath(''), []);

  const createFolder = useCallback(
    async (name: string): Promise<boolean> => {
      if (!name.trim()) {
        toast.error(t('fileManager:messages.enterFolderName', 'Please enter a folder name'));
        return false;
      }
      try {
        await apiCreateFolder({ path: resolveFullPath(), name });
        toast.success(t('fileManager:messages.folderCreated', 'Folder created successfully'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.folderError', 'Failed to create folder')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, resolveFullPath, refresh],
  );

  const deleteFile = useCallback(
    async (file: FileItem): Promise<boolean> => {
      try {
        await apiDeleteFile(file.path);
        toast.success(t('fileManager:messages.deleteSuccess'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.deleteError')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, refresh],
  );

  const renameFile = useCallback(
    async (file: FileItem, newName: string): Promise<boolean> => {
      if (!newName.trim()) {
        toast.error(t('fileManager:messages.enterFileName', 'Please enter a valid file name'));
        return false;
      }
      try {
        await apiRenameFile({ old_path: file.path, new_name: newName });
        toast.success(t('fileManager:messages.renameSuccess'));
        refresh();
        return true;
      } catch (err) {
        toast.error(`${t('fileManager:messages.renameError')}: ${getErrorMessage(errDetail(err))}`);
        return false;
      }
    },
    [t, refresh],
  );

  const downloadFile = useCallback(
    async (file: FileItem): Promise<void> => {
      if (file.type === 'directory') return;
      try {
        const blob = await downloadFileBlob(file.path);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch {
        toast.error(t('fileManager:messages.downloadError', 'Download failed'));
      }
    },
    [t],
  );

  return {
    mountpoints: mountpointsQuery.data?.mountpoints ?? EMPTY_MOUNTPOINTS,
    selectedMountpoint,
    selectMountpoint,
    currentPath,
    getFullPath: resolveFullPath,
    navigateToFolder,
    goBack,
    goHome,
    files,
    loading,
    storageInfo,
    createFolder,
    deleteFile,
    renameFile,
    downloadFile,
    refresh,
  };
}
