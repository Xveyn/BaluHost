import { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';
import { UploadProgressModal } from '../components/UploadProgressModal';

interface StorageInfo {
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
}

interface StorageMountpoint {
  id: string;
  name: string;
  type: string;
  path: string;
  size_bytes: number;
  used_bytes: number;
  available_bytes: number;
  raid_level?: string;
  status: string;
  is_default: boolean;
}

interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modifiedAt: string;
  ownerId?: number;
}

interface ApiFileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modified_at?: string;
  mtime?: string;
}

interface FileViewerProps {
  file: FileItem;
  onClose: () => void;
}

function FileViewer({ file, onClose }: FileViewerProps) {
  const [content, setContent] = useState<string>('');
  const [blobUrl, setBlobUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    loadFileContent();
    
    // Cleanup blob URL when component unmounts
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [file.path]);

  const loadFileContent = async () => {
    setLoading(true);
    setError('');
    const token = localStorage.getItem('token');
    if (!token) {
      setError('Not authenticated');
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/download/${encodeURIComponent(file.path)}`), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        
        // For images, videos, audio, PDFs - create blob URL
        if (isImageFile(file.name) || isVideoFile(file.name) || isAudioFile(file.name) || isPdfFile(file.name)) {
          const url = URL.createObjectURL(blob);
          setBlobUrl(url);
        } else {
          // For text files - convert to text
          const text = await blob.text();
          setContent(text);
        }
      } else {
        setError('Failed to load file');
      }
    } catch (err) {
      console.error('Failed to load file:', err);
      setError('Failed to load file');
    } finally {
      setLoading(false);
    }
  };

  const getFileExtension = (filename: string) => {
    return filename.split('.').pop()?.toLowerCase() || '';
  };

  const isTextFile = (filename: string) => {
    const ext = getFileExtension(filename);
    const textExtensions = ['txt', 'md', 'json', 'js', 'ts', 'jsx', 'tsx', 'css', 'html', 'xml', 'yaml', 'yml', 'log', 'py', 'java', 'c', 'cpp', 'h', 'cs', 'php', 'rb', 'go', 'rs', 'sh'];
    return textExtensions.includes(ext);
  };

  const isImageFile = (filename: string) => {
    const ext = getFileExtension(filename);
    const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
    return imageExtensions.includes(ext);
  };

  const isVideoFile = (filename: string) => {
    const ext = getFileExtension(filename);
    const videoExtensions = ['mp4', 'webm', 'ogg', 'mov', 'avi'];
    return videoExtensions.includes(ext);
  };

  const isAudioFile = (filename: string) => {
    const ext = getFileExtension(filename);
    const audioExtensions = ['mp3', 'wav', 'ogg', 'flac', 'm4a'];
    return audioExtensions.includes(ext);
  };

  const isPdfFile = (filename: string) => {
    return getFileExtension(filename) === 'pdf';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-lg p-4">
      <div className="card w-full max-w-4xl max-h-[90vh] border-slate-800/60 bg-slate-900/90 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xl font-semibold text-white">{file.name}</h3>
            <p className="text-sm text-slate-400 mt-1">{file.path}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            ✕ Close
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-slate-500">Loading file...</p>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-rose-400">{error}</p>
            </div>
          ) : isImageFile(file.name) ? (
            <div className="flex items-center justify-center p-4 bg-slate-950/50">
              <img
                src={blobUrl}
                alt={file.name}
                className="max-w-full max-h-[70vh] rounded-lg"
              />
            </div>
          ) : isVideoFile(file.name) ? (
            <div className="p-4">
              <video controls className="w-full max-h-[70vh] rounded-lg bg-black">
                <source src={blobUrl} type={`video/${getFileExtension(file.name)}`} />
                Your browser does not support the video tag.
              </video>
            </div>
          ) : isAudioFile(file.name) ? (
            <div className="flex flex-col items-center justify-center p-8">
              <div className="mb-4 text-6xl">🎵</div>
              <audio controls className="w-full max-w-md">
                <source src={blobUrl} type={`audio/${getFileExtension(file.name)}`} />
                Your browser does not support the audio tag.
              </audio>
            </div>
          ) : isPdfFile(file.name) ? (
            <div className="p-4">
              <iframe
                src={blobUrl}
                className="w-full h-[70vh] rounded-lg border border-slate-800"
                title={file.name}
              />
            </div>
          ) : isTextFile(file.name) ? (
            <pre className="p-4 text-sm text-slate-300 font-mono whitespace-pre-wrap break-words bg-slate-950/50 rounded-lg">
              {content}
            </pre>
          ) : (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-slate-500">Preview not available for this file type</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function FileManager() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
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
  const [uploadIds, setUploadIds] = useState<string[] | null>(null);
  const [mountpoints, setMountpoints] = useState<StorageMountpoint[]>([]);
  const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

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
  }, []);

  useEffect(() => {
    if (selectedMountpoint) {
      loadFiles(currentPath);
      loadStorageInfo();
    }
  }, [currentPath, selectedMountpoint]);

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

  const handleFilesUpload = async (fileList: FileList) => {
    setUploading(true);
    const token = getToken();
    if (!token) {
      setUploading(false);
      return;
    }

    // Check storage capacity
    const totalSize = Array.from(fileList).reduce((acc, file) => acc + file.size, 0);
    if (storageInfo && storageInfo.availableBytes !== null && totalSize > storageInfo.availableBytes) {
      toast.error(`Not enough storage space. Need ${formatFileSize(totalSize)}, but only ${formatFileSize(storageInfo.availableBytes)} available.`);
      setUploading(false);
      return;
    }

    const formData = new FormData();

    Array.from(fileList).forEach(file => {
      formData.append('files', file);
    });
    // Use full path with mountpoint
    formData.append('path', getFullPath());

    try {
      const response = await fetch(buildApiUrl('/api/files/upload'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (response.ok) {
        const result = await response.json();
        const ids = result.upload_ids || [];
        
        // Show progress modal if upload IDs are available
        if (ids.length > 0) {
          setUploadIds(ids);
        } else {
          toast.success('Files uploaded successfully!');
        }
        
        // Invalidate cache and reload
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        sessionStorage.removeItem('storage_info_cache');
        loadFiles(currentPath, false);
        loadStorageInfo();
      } else {
        const error = await response.json();
        toast.error(`Upload failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Upload failed:', err);
      toast.error('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;

    await handleFilesUpload(fileList);
    e.target.value = '';
  };

  const handleFolderUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;

    await handleFilesUpload(fileList);
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
      toast.error('Download failed. Please try again.');
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error('Please enter a folder name');
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
        toast.success('Folder created successfully!');
        setShowNewFolderDialog(false);
        setNewFolderName('');
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        loadFiles(currentPath, false);
      } else {
        const error = await response.json();
        toast.error(`Failed to create folder: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Create folder failed:', err);
      toast.error('Failed to create folder. Please try again.');
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
        toast.success(`${fileToDelete.type === 'directory' ? 'Folder' : 'File'} deleted successfully!`);
        setShowDeleteDialog(false);
        setFileToDelete(null);
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        sessionStorage.removeItem('storage_info_cache');
        loadFiles(currentPath, false);
        loadStorageInfo();
      } else {
        const error = await response.json();
        toast.error(`Delete failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Delete failed:', err);
      toast.error('Delete failed. Please try again.');
    }
  };

  const startRename = (file: FileItem) => {
    setFileToRename(file);
    setNewFileName(file.name);
    setShowRenameDialog(true);
  };

  const handleRename = async () => {
    if (!fileToRename || !newFileName.trim()) {
      toast.error('Please enter a valid file name');
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
        toast.success('Renamed successfully!');
        setShowRenameDialog(false);
        setFileToRename(null);
        setNewFileName('');
        sessionStorage.removeItem(`files_cache_${currentPath}`);
        loadFiles(currentPath, false);
      } else {
        const error = await response.json();
        toast.error(`Rename failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Rename failed:', err);
      toast.error('Rename failed. Please try again.');
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
      
      await handleFilesUpload(dt.files);
    }
  };

  const handleViewFile = (file: FileItem) => {
    setViewingFile(file);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
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
    setCurrentPath(parts.join('/'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">
            File Manager
          </h1>
          <p className="mt-1 text-sm text-slate-400">Browse, upload, and organise your vaults</p>
          {storageInfo && (
            <div className="mt-2 text-xs text-slate-500">
              Storage: {formatFileSize(storageInfo.usedBytes)} / {formatFileSize(storageInfo.totalBytes)} used
              <span className="ml-2 text-sky-400">({formatFileSize(storageInfo.availableBytes)} available)</span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setShowNewFolderDialog(true)}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-500/40 hover:text-white"
          >
            + New Folder
          </button>
          <label className={`btn btn-primary cursor-pointer ${uploading ? 'opacity-70' : ''}`}>
            {uploading ? 'Uploading...' : '↑ Upload Files'}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
          <label className={`rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-500/40 hover:text-white cursor-pointer ${uploading ? 'opacity-70' : ''}`}>
            📁 Upload Folder
            <input
              ref={folderInputRef}
              type="file"
              {...({ webkitdirectory: '', directory: '' } as any)}
              multiple
              className="hidden"
              onChange={handleFolderUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {/* Storage Drive Selector */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">Storage Devices:</span>
          {mountpoints.map((mp) => (
            <button
              key={mp.id}
              onClick={() => {
                setSelectedMountpoint(mp);
                setCurrentPath(''); // Reset to root when switching drives
              }}
              className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition ${
                selectedMountpoint?.id === mp.id
                  ? 'border-sky-500/50 bg-sky-500/10 text-sky-200'
                  : 'border-slate-700/70 bg-slate-950/70 text-slate-300 hover:border-sky-500/40 hover:text-white'
              }`}
            >
              <span className="text-base">
                {mp.type === 'raid' ? '💾' : mp.type === 'dev-storage' ? '🔧' : '💿'}
              </span>
              <div className="flex flex-col items-start">
                <span className="font-semibold">{mp.name}</span>
                <span className="text-xs text-slate-400">
                  {formatFileSize(mp.used_bytes)} / {formatFileSize(mp.size_bytes)}
                  {mp.raid_level && ` • ${mp.raid_level.toUpperCase()}`}
                  {mp.status !== 'optimal' && (
                    <span className="ml-1 text-amber-400">⚠ {mp.status}</span>
                  )}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Breadcrumb Navigation */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
          <button
            onClick={() => setCurrentPath('')}
            className="rounded-full border border-slate-700/70 bg-slate-950/70 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white"
          >
            Home
          </button>
          {currentPath && (
            <>
              <span className="text-slate-600">/</span>
              <button
                onClick={goBack}
                className="rounded-full border border-slate-700/70 bg-slate-950/70 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white"
              >
                ← Back
              </button>
              <span className="text-slate-600">/</span>
              <span className="rounded-full border border-slate-800/70 bg-slate-900/80 px-3 py-1.5 text-xs uppercase tracking-[0.25em] text-slate-200">
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
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
                  <th className="px-6 py-4">Name</th>
                  <th className="px-6 py-4">Type</th>
                  <th className="px-6 py-4">Size</th>
                  <th className="px-6 py-4">Modified</th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {files.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-500">
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
                              ? 'border-sky-500/20 bg-sky-500/10 text-sky-200'
                              : 'border-slate-800 bg-slate-900/70 text-slate-400'
                          }`}>
                            {file.type === 'directory' ? '📁' : '📄'}
                          </span>
                          <span className="truncate font-medium group-hover:text-white">
                            {file.name}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-xs uppercase tracking-[0.25em] text-slate-500">
                        {file.type}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {file.type === 'file' ? formatFileSize(file.size) : '—'}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {new Date(file.modifiedAt).toLocaleString()}
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
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/70">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-rose-500/30 bg-slate-900/75">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/70">
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

      {/* Upload Progress Modal */}
      {uploadIds && uploadIds.length > 0 && (
        <UploadProgressModal
          uploadIds={uploadIds}
          onClose={() => {
            setUploadIds(null);
            toast.success('Files uploaded successfully!');
          }}
        />
      )}
    </div>
  );
}
