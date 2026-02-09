import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { buildApiUrl, getFilePermissions, setFilePermissions } from '../lib/api';
import { VersionHistoryModal } from '../components/vcl/VersionHistoryModal';
import { vclApi } from '../api/vcl';
import { formatBytes, formatNumber } from '../lib/formatters';
import { FileViewer } from '../components/file-manager/FileViewer';
import { StorageSelector } from '../components/file-manager/StorageSelector';
import { PermissionEditor } from '../components/file-manager/PermissionEditor';
import { useUpload } from '../contexts/UploadContext';
import type { StorageInfo, StorageMountpoint, FileItem, ApiFileItem, PermissionRule } from '../components/file-manager/types';

interface FileManagerProps {
  user: {
    id: number;
    username: string;
    role: string;
  };
}

export default function FileManager({ user }: FileManagerProps) {
                    const { t } = useTranslation(['fileManager', 'common']);
                    // User-Liste State ganz oben definieren
                    const [allUsers, setAllUsers] = useState<Array<{ id: string; username: string }>>([]);
                  // User-Liste immer beim Mount laden
                  useEffect(() => {
                    const token = getToken(false);
                    if (!token) return;
                    fetch(buildApiUrl('/api/users/'), {
                      headers: { 'Authorization': `Bearer ${token}` }
                    })
                      .then(res => res.ok ? res.json() : null)
                      .then(data => {
                        if (data && Array.isArray(data.users)) {
                          setAllUsers(data.users.map((u: any) => ({ id: String(u.id), username: u.username })));
                          console.log('User-Liste:', data.users);
                        } else {
                          console.log('User-API liefert keine User:', data);
                        }
                      })
                      .catch((err) => { console.log('User-API Fehler:', err); });
                  }, []);
                  // User-Liste State ganz oben definieren
                  // (Deklaration bleibt nur einmal bestehen, doppelte Zeile entfernt)
                  // Logging erst nach useState-Definition
                  useEffect(() => {
                    console.log('Aktuelle User-Liste:', allUsers);
                  }, [allUsers]);
      // State für Rechte-Modal
      const [showEditPermissionsModal, setShowEditPermissionsModal] = useState(false);
      const [fileToEditPermissions, setFileToEditPermissions] = useState<FileItem | null>(null);
      // Neue State für Berechtigungsregeln
      const [editRules, setEditRules] = useState<PermissionRule[]>([]);
      // Nur eine Deklaration von allUsers/setAllUsers!
      // (Deklaration bleibt nur einmal bestehen, doppelte Zeile entfernt)

      // Hilfsfunktion: Ist aktueller User Owner/Admin?
      function isCurrentUserOwnerOrAdmin(ownerId: number | undefined) {
        if (!user) return false;
        return user.role === 'admin' || String(ownerId) === String(user.id);
      }

      // Modal: Rechte bearbeiten
      async function handleEditPermissionsSave() {
        if (!fileToEditPermissions) return;
        try {
          // Sende alle Regeln in einem Request
          await setFilePermissions({
            path: fileToEditPermissions.path,
            owner_id: fileToEditPermissions.ownerId ?? user.id,
            rules: editRules.map(rule => ({
              user_id: Number(rule.userId),
              can_view: rule.canView,
              can_edit: rule.canEdit,
              can_delete: rule.canDelete,
            }))
          });
          toast.success(t('fileManager:messages.permissionsSaved'));
        } catch (err) {
          toast.error(t('fileManager:messages.permissionsError'));
        }
        setShowEditPermissionsModal(false);
        setFileToEditPermissions(null);
      }
    // User-Cache für Ownernamen
    const [userCache, setUserCache] = useState<Record<string, string>>({});
    const [files, setFiles] = useState<FileItem[]>([]);

    useEffect(() => {
      const ownerIds = files
        .map(f => f.ownerId)
        .filter(id => typeof id === 'string' || typeof id === 'number')
        .map(id => String(id));
      const uniqueIds = Array.from(new Set(ownerIds.filter(id => id !== 'null' && id !== 'undefined')));
      if (uniqueIds.length === 0) return;
      const token = getToken(false);
      if (!token) return;
        fetch(buildApiUrl('/api/users/'), {
          headers: { 'Authorization': `Bearer ${token}` }
        })
          .then(res => res.ok ? res.json() : null)
          .then(data => {
            if (data && Array.isArray(data.users)) {
              const cache: Record<string, string> = {};
              for (const user of data.users) {
                cache[String(user.id)] = user.username;
              }
              setUserCache(cache);
              console.log('User-Liste:', data.users);
            } else {
              console.log('User-API liefert keine User:', data);
            }
          })
          .catch((err) => { console.log('User-API Fehler:', err); });
    }, [files]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);
  const { startUpload, isUploading, onUploadsComplete } = useUpload();
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<FileItem | null>(null);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileItem | null>(null);
  const [newFileName, setNewFileName] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [viewingFile, setViewingFile] = useState<FileItem | null>(null);
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);
  const [mountpoints, setMountpoints] = useState<StorageMountpoint[]>([]);
  const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // VCL State
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [versionHistoryFile, setVersionHistoryFile] = useState<FileItem | null>(null);
  const [versionCounts, setVersionCounts] = useState<Record<number, number>>({});
  const [vclQuota, setVclQuota] = useState<{
    usagePercent: number;
    warning: 'warning' | 'critical' | null;
    current: number;
    max: number;
  } | null>(null);

  const getToken = (notify = true): string | null => {
    const token = localStorage.getItem('token');
    if (!token && notify) {
      toast.error('Session expired. Please sign in again.');
    }
    return token;
  };

  const getErrorMessage = (error: any): string => {
    if (!error) return 'Unknown error';
    return error.error ?? error.detail ?? 'Unknown error';
  };

    useEffect(() => {
      loadMountpoints();
      loadVclQuota(); // Load quota on mount
    }, []);

    // Reload files + storage when uploads complete
    useEffect(() => {
      return onUploadsComplete(() => {
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        sessionStorage.removeItem('storage_info_cache');
        loadFiles(currentPath, false);
        loadStorageInfo();
        loadVclQuota();
      });
    }, [currentPath, onUploadsComplete]);

    useEffect(() => {
      if (selectedMountpoint) {
        loadFiles(currentPath);
        loadStorageInfo();
      }
    }, [currentPath, selectedMountpoint]);

    // Load VCL Quota
    const loadVclQuota = async () => {
      try {
        const quota = await vclApi.getUserQuota();
        // Determine warning level based on usage percent
        let warningLevel: 'warning' | 'critical' | null = null;
        if (quota.usage_percent >= 95) {
          warningLevel = 'critical';
        } else if (quota.usage_percent >= 80) {
          warningLevel = 'warning';
        }
        
        setVclQuota({
          usagePercent: quota.usage_percent,
          warning: warningLevel,
          current: quota.current_usage_bytes,
          max: quota.max_size_bytes,
        });
        
        // Show toast if warning/critical
        if (warningLevel === 'critical') {
          toast.error(
            `VCL Storage Critical: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
            { duration: 8000 }
          );
        } else if (warningLevel === 'warning') {
          toast(
            `VCL Storage Warning: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
            { duration: 6000, icon: '⚠️' }
          );
        }
      } catch (err) {
        // Silently ignore quota errors
      }
    };

    // Load version counts for all files with file_id
    useEffect(() => {
      const loadVersionCounts = async () => {
        const fileIds = files
          .filter(f => f.type === 'file' && f.file_id)
          .map(f => f.file_id!);
        
        if (fileIds.length === 0) return;

        try {
          const counts: Record<number, number> = {};
          await Promise.all(
            fileIds.map(async (fileId) => {
              try {
                const response = await vclApi.getFileVersions(fileId);
                counts[fileId] = response.total;
              } catch (err) {
                // Ignore errors for individual files
              }
            })
          );
          setVersionCounts(counts);
        } catch (err) {
          console.error('Failed to load version counts:', err);
        }
      };

      loadVersionCounts();
    }, [files]);

    // Ownernamen nachladen, wenn Files geladen werden
    useEffect(() => {
      const fetchOwnerNames = async (ownerIds: (string | number)[]) => {
        const uniqueIds = Array.from(new Set(ownerIds.filter(id => id !== undefined && id !== null && String(id) !== 'null')));
        if (uniqueIds.length === 0) return;
        const token = getToken(false);
        if (!token) return;
        try {
          const response = await fetch(buildApiUrl('/api/users/'), {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (response.ok) {
            const data = await response.json();
            const cache: Record<string, string> = {};
            for (const user of data.users) {
              cache[user.id] = user.username;
            }
            setUserCache(cache);
          }
        } catch (err) {
          // ignore
        }
      };
      const ownerIds = files.map(f => f.ownerId).filter(id => id !== undefined && id !== null && String(id) !== 'null') as (string | number)[];
      fetchOwnerNames(ownerIds);
    }, [files]);

  const loadMountpoints = async () => {
    const token = getToken(false);
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl('/api/files/mountpoints'), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setMountpoints(data.mountpoints || []);
        
        // Set default mountpoint
        const defaultMp = data.mountpoints.find((mp: StorageMountpoint) => mp.is_default) 
                         || data.mountpoints[0];
        if (defaultMp) {
          setSelectedMountpoint(defaultMp);
          setCurrentPath(''); // Start at root of selected mountpoint
        }
      } else {
        toast.error('Failed to load storage devices');
      }
    } catch (err) {
      console.error('Failed to load mountpoints:', err);
      toast.error('Failed to load storage devices');
    }
  };

  const loadStorageInfo = async () => {
    if (!selectedMountpoint) return;
    
    // Use mountpoint storage info directly
    const info = {
      totalBytes: selectedMountpoint.size_bytes,
      usedBytes: selectedMountpoint.used_bytes,
      availableBytes: selectedMountpoint.available_bytes
    };
    setStorageInfo(info);
  };

  // Helper function to construct full path with mountpoint
  const getFullPath = (relativePath: string = currentPath): string => {
    if (!selectedMountpoint) return relativePath;
    
    // Dev storage uses flat paths, RAID arrays need mountpoint prefix
    if (selectedMountpoint.type === 'dev-storage') {
      return relativePath;
    }
    
    // For RAID arrays, prepend mountpoint path
    // Remove leading slash from relativePath if present to avoid double slashes
    const cleanRelativePath = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
    return cleanRelativePath ? `${selectedMountpoint.path}/${cleanRelativePath}` : selectedMountpoint.path;
  };

  const loadFiles = async (path: string, useCache = true) => {
    if (!selectedMountpoint) return;
    
    // Construct full path with mountpoint
    const fullPath = getFullPath(path);
    
    // Try to load from cache first
    if (useCache) {
      const cacheKey = `files_cache_${fullPath}`;
      const cachedData = sessionStorage.getItem(cacheKey);
      if (cachedData) {
        try {
          const cached = JSON.parse(cachedData);
          setFiles(cached.files);
          // Continue loading in background
        } catch (err) {
          console.error('Failed to parse cache:', err);
        }
      }
    }

    setLoading(true);
    const token = getToken(false);
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/list?path=${encodeURIComponent(fullPath)}`), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();
      if (Array.isArray(data.files)) {
        const mappedFiles: FileItem[] = (data.files as ApiFileItem[]).map((file) => ({
          name: file.name,
          path: file.path,
          size: file.size,
          type: file.type,
          modifiedAt: file.modified_at ?? file.mtime ?? new Date().toISOString(),
          ownerId: (file as any).ownerId ?? (file as any).owner_id,
          ownerName: (file as any).ownerName ?? (file as any).owner_name,
          file_id: (file as any).file_id,
        }));
        setFiles(mappedFiles);
        
        // Cache the results
        const cacheKey = `files_cache_${fullPath}`;
        sessionStorage.setItem(cacheKey, JSON.stringify({ files: mappedFiles, timestamp: Date.now() }));
      }
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;
    startUpload(fileList, getFullPath(), storageInfo?.availableBytes);
    e.target.value = '';
  };

  const handleFolderUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;
    startUpload(fileList, getFullPath(), storageInfo?.availableBytes);
    e.target.value = '';
  };

  const handleDownload = async (file: FileItem) => {
    if (file.type === 'directory') return;

    const token = getToken();
    if (!token) {
      return;
    }
    const url = buildApiUrl(`/api/files/download/${encodeURIComponent(file.path)}`);

    try {
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } else {
        toast.error('Download failed');
      }
    } catch (err) {
      console.error('Download failed:', err);
      toast.error(t('fileManager:messages.downloadError', 'Download failed'));
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error(t('fileManager:messages.enterFolderName', 'Please enter a folder name'));
      return;
    }

    const token = getToken();
    if (!token) {
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/files/folder'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          path: getFullPath(),
          name: newFolderName
        })
      });

      if (response.ok) {
        toast.success(t('fileManager:messages.folderCreated', 'Folder created successfully'));
        setShowNewFolderDialog(false);
        setNewFolderName('');
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        loadFiles(currentPath, false);
      } else {
        const error = await response.json();
        toast.error(`${t('fileManager:messages.folderError', 'Failed to create folder')}: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Create folder failed:', err);
      toast.error(t('fileManager:messages.folderError', 'Failed to create folder'));
    }
  };

  const confirmDelete = (file: FileItem) => {
    setFileToDelete(file);
    setShowDeleteDialog(true);
  };

  const handleDelete = async () => {
    if (!fileToDelete) return;

    const token = getToken();
    if (!token) {
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/${encodeURIComponent(fileToDelete.path)}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        toast.success(t('fileManager:messages.deleteSuccess'));
        setShowDeleteDialog(false);
        setFileToDelete(null);
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        sessionStorage.removeItem('storage_info_cache');
        loadFiles(currentPath, false);
        loadStorageInfo();
      } else {
        const error = await response.json();
        toast.error(`${t('fileManager:messages.deleteError')}: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Delete failed:', err);
      toast.error(t('fileManager:messages.deleteError'));
    }
  };

  const startRename = (file: FileItem) => {
    setFileToRename(file);
    setNewFileName(file.name);
    setShowRenameDialog(true);
  };

  const handleRename = async () => {
    if (!fileToRename || !newFileName.trim()) {
      toast.error(t('fileManager:messages.enterFileName', 'Please enter a valid file name'));
      return;
    }

    const token = localStorage.getItem('token');

    try {
      const response = await fetch(buildApiUrl('/api/files/rename'), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          old_path: fileToRename.path,
          new_name: newFileName
        })
      });

      if (response.ok) {
        toast.success(t('fileManager:messages.renameSuccess'));
        setShowRenameDialog(false);
        setFileToRename(null);
        setNewFileName('');
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        loadFiles(currentPath, false);
      } else {
        const error = await response.json();
        toast.error(`${t('fileManager:messages.renameError')}: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Rename failed:', err);
      toast.error(t('fileManager:messages.renameError'));
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const traverseFileTree = async (item: any, path = ''): Promise<File[]> => {
    const files: File[] = [];
    
    if (item.isFile) {
      return new Promise((resolve) => {
        item.file((file: File) => {
          const newFile = new File([file], path + file.name, { type: file.type });
          Object.defineProperty(newFile, 'webkitRelativePath', {
            value: path + file.name,
            writable: false
          });
          resolve([newFile]);
        });
      });
    } else if (item.isDirectory) {
      const dirReader = item.createReader();
      return new Promise((resolve) => {
        const readEntries = () => {
          dirReader.readEntries(async (entries: any[]) => {
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
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const items = e.dataTransfer.items;
    if (!items) return;

    const allFiles: File[] = [];
    
    for (let i = 0; i < items.length; i++) {
      const item = items[i].webkitGetAsEntry();
      if (item) {
        const files = await traverseFileTree(item);
        allFiles.push(...files);
      }
    }

    if (allFiles.length > 0) {
      const dt = new DataTransfer();
      allFiles.forEach(file => dt.items.add(file));
      startUpload(dt.files, getFullPath(), storageInfo?.availableBytes);
    }
  };

  const handleViewFile = (file: FileItem) => {
    setViewingFile(file);
  };

  const navigateToFolder = (folderPath: string) => {
    // Remove mountpoint prefix if present to get relative path
    if (selectedMountpoint && selectedMountpoint.type !== 'dev-storage') {
      const mountpointPrefix = selectedMountpoint.path;
      if (folderPath.startsWith(mountpointPrefix)) {
        // Remove mountpoint prefix and leading slash
        const relativePath = folderPath.slice(mountpointPrefix.length).replace(/^\//, '');
        setCurrentPath(relativePath);
        return;
      }
    }
    setCurrentPath(folderPath);
  };

  const goBack = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    const parentPath = parts.join('/');

    // If navigating up from a shared folder (not own home, not Shared),
    // redirect to "Shared with me" instead of going to a foreign root
    if (
      currentPath &&
      !currentPath.startsWith(user.username + '/') &&
      currentPath !== user.username &&
      !currentPath.startsWith('Shared/') &&
      currentPath !== 'Shared' &&
      currentPath !== 'Shared with me'
    ) {
      // We're inside a shared path — check if parent would leave the shared tree
      const topLevel = parts[0] || '';
      if (!topLevel || (topLevel !== user.username && topLevel !== 'Shared' && topLevel !== 'Shared with me')) {
        setCurrentPath('Shared with me');
        return;
      }
    }

    setCurrentPath(parentPath);
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            File Manager
          </h1>
          <p className="mt-1 text-sm text-slate-400">Browse, upload, and organise your vaults</p>
          {storageInfo && (
            <div className="mt-2 text-xs text-slate-500">
              <span className="hidden sm:inline">Storage: </span>
              {formatBytes(storageInfo.usedBytes)} / {formatBytes(storageInfo.totalBytes)} used
              <span className="ml-2 text-sky-400">({formatBytes(storageInfo.availableBytes)} available)</span>
            </div>
          )}
          {vclQuota && (
            <div className="mt-1 text-xs">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${
                vclQuota.warning === 'critical'
                  ? 'bg-red-500/20 text-red-300 border border-red-500/30'
                  : vclQuota.warning === 'warning'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
              }`}>
                {vclQuota.warning === 'critical' && '🔴'}
                {vclQuota.warning === 'warning' && '⚠️'}
                {!vclQuota.warning && '📦'}
                VCL: {formatNumber(vclQuota.usagePercent, 1)}% ({formatBytes(vclQuota.current)} / {formatBytes(vclQuota.max)})
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <button
            onClick={() => setShowNewFolderDialog(true)}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium text-slate-200 transition hover:border-sky-500/40 hover:text-white touch-manipulation active:scale-95"
          >
            <span className="hidden sm:inline">+ New Folder</span>
            <span className="sm:hidden">+ Folder</span>
          </button>
          <label className={`btn btn-primary cursor-pointer text-xs sm:text-sm px-3 sm:px-5 py-2 sm:py-2.5 touch-manipulation active:scale-95 ${isUploading ? 'opacity-70' : ''}`}>
            <span className="hidden sm:inline">{isUploading ? 'Uploading...' : '↑ Upload Files'}</span>
            <span className="sm:hidden">↑ Files</span>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleUpload}
              disabled={isUploading}
            />
          </label>
          <label className={`hidden sm:flex rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-500/40 hover:text-white cursor-pointer touch-manipulation active:scale-95 ${isUploading ? 'opacity-70' : ''}`}>
            📁 Upload Folder
            <input
              ref={folderInputRef}
              type="file"
              {...({ webkitdirectory: '', directory: '' } as any)}
              multiple
              className="hidden"
              onChange={handleFolderUpload}
              disabled={isUploading}
            />
          </label>
        </div>
      </div>

      {/* Storage Drive Selector */}
      <StorageSelector
        mountpoints={mountpoints}
        selectedMountpoint={selectedMountpoint}
        onSelect={(mp) => {
          setSelectedMountpoint(mp);
          setCurrentPath(''); // Reset to root when switching drives
        }}
      />

      {/* Breadcrumb Navigation */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs sm:text-sm text-slate-400">
          <button
            onClick={() => setCurrentPath('')}
            className="rounded-full border border-slate-700/70 bg-slate-950/70 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium uppercase tracking-[0.15em] sm:tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white touch-manipulation active:scale-95"
          >
            {t('fileManager:labels.home', 'Home')}
          </button>
          {currentPath && (
            <>
              <span className="text-slate-600">/</span>
              <button
                onClick={goBack}
                className="rounded-full border border-slate-700/70 bg-slate-950/70 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium uppercase tracking-[0.15em] sm:tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white touch-manipulation active:scale-95"
              >
                ← Back
              </button>
              <span className="text-slate-600 hidden sm:inline">/</span>
              <span className="rounded-full border border-slate-800/70 bg-slate-900/80 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs uppercase tracking-[0.15em] sm:tracking-[0.25em] text-slate-200 truncate max-w-[150px] sm:max-w-none">
                {currentPath || '/'}
              </span>
            </>
          )}
        </div>
      </div>

      {loading && files.length === 0 ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">Loading files...</p>
        </div>
      ) : (
        <div 
          className={`card border-slate-800/60 bg-slate-900/55 transition-all relative ${dragActive ? 'border-sky-500 bg-sky-500/10' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          {loading && files.length > 0 && (
            <div className="absolute top-2 right-2 z-10 flex items-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200">
              <div className="h-2 w-2 animate-pulse rounded-full bg-sky-400"></div>
              Updating...
            </div>
          )}
          {dragActive && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-sky-500/20 backdrop-blur-sm rounded-2xl border-2 border-dashed border-sky-500">
              <p className="text-lg font-semibold text-sky-200">Drop files or folders here</p>
            </div>
          )}
          {/* Desktop Table View */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
                  <th className="px-6 py-4">Name</th>
                  <th className="px-6 py-4">Type</th>
                  <th className="px-6 py-4">Size</th>
                  <th className="px-6 py-4">Modified</th>
                  <th className="px-6 py-4">Owner</th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {files.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
                      No files found
                    </td>
                  </tr>
                ) : (
                  files.map((file) => (
                    <tr
                      key={file.path}
                      className="group transition hover:bg-slate-900/70"
                    >
                      <td
                        className="px-6 py-4"
                        onClick={() => file.type === 'directory' && navigateToFolder(file.path)}
                      >
                        <div className="flex cursor-pointer items-center gap-3 text-sm text-slate-200">
                          <span className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base ${
                            file.type === 'directory'
                              ? file.name === 'Shared'
                                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200'
                                : 'border-sky-500/20 bg-sky-500/10 text-sky-200'
                              : 'border-slate-800 bg-slate-900/70 text-slate-400'
                          }`}>
                            {file.type === 'directory' ? (file.name === 'Shared' ? '👥' : '📁') : '📄'}
                          </span>
                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            <span className="truncate font-medium group-hover:text-white">
                              {file.name}
                            </span>
                            {file.type === 'file' && file.file_id && versionCounts[file.file_id] > 0 && (
                              <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-200">
                                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                {versionCounts[file.file_id]}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-xs uppercase tracking-[0.25em] text-slate-500">
                        {file.type}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {file.type === 'file' ? formatBytes(file.size) : '—'}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {new Date(file.modifiedAt).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-sm text-sky-400 font-mono">
                        {file.ownerName && file.ownerName !== 'null'
                          ? file.ownerName
                          : (file.ownerId !== undefined && file.ownerId !== null && userCache[file.ownerId]
                              ? userCache[file.ownerId]
                              : (file.ownerId !== undefined && file.ownerId !== null
                                  ? `UID ${file.ownerId}`
                                  : '—'))}
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          {file.type === 'file' && (
                            <>
                              <button
                                onClick={() => handleViewFile(file)}
                                className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400/40 hover:bg-emerald-500/20"
                              >
                                👁 View
                              </button>
                              <button
                                onClick={() => handleDownload(file)}
                                className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400/40 hover:bg-sky-500/20"
                              >
                                ↓ Download
                              </button>
                              {file.file_id && (
                                <button
                                  onClick={() => {
                                    setVersionHistoryFile(file);
                                    setShowVersionHistory(true);
                                  }}
                                  className="rounded-xl border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-200 transition hover:border-violet-400/40 hover:bg-violet-500/20"
                                >
                                  <svg className="inline-block h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  Versionen
                                  {versionCounts[file.file_id] > 0 && (
                                    <span className="ml-1 inline-flex items-center justify-center rounded-full bg-violet-400/20 px-1.5 py-0.5 text-[10px] font-bold">
                                      {versionCounts[file.file_id]}
                                    </span>
                                  )}
                                </button>
                              )}
                            </>
                          )}
                          <button
                            onClick={() => startRename(file)}
                            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
                          >
                            ✎ Rename
                          </button>
                          <button
                            onClick={() => confirmDelete(file)}
                            className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-400/40 hover:bg-rose-500/20"
                          >
                            🗑 Delete
                          </button>
                          {/* Owner/Admin: Edit Permissions */}
                          {(isCurrentUserOwnerOrAdmin(file.ownerId)) && (
                            <button
                              onClick={async () => {
                                setFileToEditPermissions(file);
                                setShowEditPermissionsModal(true);
                                // Lade existierende Regeln (Demo: nur Owner)
                                try {
                                  const perms = await getFilePermissions(file.path);
                                  if (Array.isArray(perms.rules) && perms.rules.length > 0) {
                                    setEditRules(perms.rules.map((rule: any) => ({
                                      userId: String(rule.user_id),
                                      canView: rule.can_view,
                                      canEdit: rule.can_edit,
                                      canDelete: rule.can_delete,
                                    })));
                                  } else {
                                    setEditRules([
                                      {
                                        userId: String(perms.owner_id ?? ''),
                                        canView: true,
                                        canEdit: true,
                                        canDelete: true,
                                      }
                                    ]);
                                  }
                                } catch {
                                  setEditRules([
                                    {
                                      userId: String(file.ownerId ?? ''),
                                      canView: true,
                                      canEdit: true,
                                      canDelete: true,
                                    }
                                  ]);
                                }
                              }}
                              className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-xs font-medium text-indigo-200 transition hover:border-indigo-400/40 hover:bg-indigo-500/20"
                            >
                              ⚙ Rechte bearbeiten
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile Card View */}
          <div className="lg:hidden space-y-3">
            {files.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-500">
                No files found
              </div>
            ) : (
              files.map((file) => (
                <div
                  key={file.path}
                  className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4 space-y-3 touch-manipulation active:bg-slate-900/70 transition"
                >
                  {/* File Header */}
                  <div
                    onClick={() => file.type === 'directory' && navigateToFolder(file.path)}
                    className="flex items-center gap-3 cursor-pointer"
                  >
                    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-lg ${
                      file.type === 'directory'
                        ? file.name === 'Shared'
                          ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200'
                          : 'border-sky-500/20 bg-sky-500/10 text-sky-200'
                        : 'border-slate-800 bg-slate-900/70 text-slate-400'
                    }`}>
                      {file.type === 'directory' ? (file.name === 'Shared' ? '👥' : '📁') : '📄'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-slate-200 truncate">{file.name}</p>
                        {file.type === 'file' && file.file_id && versionCounts[file.file_id] > 0 && (
                          <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-200">
                            <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {versionCounts[file.file_id]}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                        <span className="uppercase tracking-wider">{file.type}</span>
                        {file.type === 'file' && (
                          <>
                            <span>•</span>
                            <span>{formatBytes(file.size)}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* File Meta */}
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                    <div>
                      <span className="text-slate-600">Modified: </span>
                      {new Date(file.modifiedAt).toLocaleDateString()}
                    </div>
                    <div>
                      <span className="text-slate-600">Owner: </span>
                      <span className="text-sky-400 font-mono">
                        {file.ownerName && file.ownerName !== 'null'
                          ? file.ownerName
                          : (file.ownerId !== undefined && file.ownerId !== null && userCache[file.ownerId]
                              ? userCache[file.ownerId]
                              : (file.ownerId !== undefined && file.ownerId !== null
                                  ? `UID ${file.ownerId}`
                                  : '—'))}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/40">
                    {file.type === 'file' && (
                      <>
                        <button
                          onClick={() => handleViewFile(file)}
                          className="flex-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-200 transition hover:border-emerald-400/40 hover:bg-emerald-500/20 touch-manipulation active:scale-95"
                        >
                          👁 View
                        </button>
                        <button
                          onClick={() => handleDownload(file)}
                          className="flex-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs font-medium text-sky-200 transition hover:border-sky-400/40 hover:bg-sky-500/20 touch-manipulation active:scale-95"
                        >
                          ↓ Download
                        </button>
                      </>
                    )}
                    {file.type === 'file' && file.file_id && (
                      <button
                        onClick={() => {
                          setVersionHistoryFile(file);
                          setShowVersionHistory(true);
                        }}
                        className="w-full rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs font-medium text-violet-200 transition hover:border-violet-400/40 hover:bg-violet-500/20 touch-manipulation active:scale-95"
                      >
                        <svg className="inline-block h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Versionen anzeigen
                        {versionCounts[file.file_id] > 0 && (
                          <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-violet-400/20 px-2 py-0.5 text-[10px] font-bold">
                            {versionCounts[file.file_id]}
                          </span>
                        )}
                      </button>
                    )}
                    <button
                      onClick={() => startRename(file)}
                      className="flex-1 rounded-lg border border-slate-700/70 bg-slate-900/70 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white touch-manipulation active:scale-95"
                    >
                      ✎ Rename
                    </button>
                    <button
                      onClick={() => confirmDelete(file)}
                      className="flex-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 transition hover:border-rose-400/40 hover:bg-rose-500/20 touch-manipulation active:scale-95"
                    >
                      🗑
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
            <h3 className="text-xl font-semibold text-white">Create New Folder</h3>
            <p className="mt-2 text-sm text-slate-400">Organise your storage pool with a dedicated directory.</p>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Enter folder name"
              className="input mt-5"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
            />
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowNewFolderDialog(false);
                  setNewFolderName('');
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFolder}
                className="btn btn-primary"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && fileToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl">
          <div className="card w-full max-w-md border-rose-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(220,38,38,0.3)]">
            <h3 className="text-xl font-semibold text-white">Confirm Delete</h3>
            <p className="mt-3 text-sm text-slate-400">
              Are you sure you want to remove <span className="font-semibold text-slate-100">{fileToDelete.name}</span>?
              {fileToDelete.type === 'directory' && <span className="text-amber-300"> All nested items will also be deleted.</span>}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  setFileToDelete(null);
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="rounded-xl border border-rose-500/50 bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:border-rose-400 hover:bg-rose-500/30"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Dialog */}
      {showRenameDialog && fileToRename && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
            <h3 className="text-xl font-semibold text-white">Rename {fileToRename.type === 'directory' ? 'Folder' : 'File'}</h3>
            <p className="mt-3 text-sm text-slate-400">Update the display name without affecting the contents.</p>
            <input
              type="text"
              value={newFileName}
              onChange={(e) => setNewFileName(e.target.value)}
              placeholder="Enter new name"
              className="input mt-5"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleRename()}
            />
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowRenameDialog(false);
                  setFileToRename(null);
                  setNewFileName('');
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleRename}
                className="btn btn-primary"
              >
                Rename
              </button>
            </div>
          </div>
        </div>
      )}

      {/* File Viewer Modal */}
      {viewingFile && (
        <FileViewer file={viewingFile} onClose={() => setViewingFile(null)} />
      )}

      {/* Version History Modal */}
      {showVersionHistory && versionHistoryFile && versionHistoryFile.file_id && (
        <VersionHistoryModal
          fileId={versionHistoryFile.file_id}
          fileName={versionHistoryFile.name}
          onClose={() => {
            setShowVersionHistory(false);
            setVersionHistoryFile(null);
          }}
          onVersionRestored={() => {
            // Reload files to show updated version count
            loadFiles(currentPath, false);
          }}
        />
      )}

      {/* Edit Permissions Modal */}
      {showEditPermissionsModal && fileToEditPermissions && (
        <PermissionEditor
          file={fileToEditPermissions}
          rules={editRules}
          allUsers={allUsers}
          onRulesChange={setEditRules}
          onSave={handleEditPermissionsSave}
          onClose={() => {
            setShowEditPermissionsModal(false);
            setFileToEditPermissions(null);
          }}
        />
      )}
    </div>
  );
}
