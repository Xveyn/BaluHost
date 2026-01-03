import { useState, useEffect } from 'react';
import { ChevronRight, Folder, File, HardDrive, RefreshCw, Upload, FolderPlus, Trash2, Edit2, Download } from 'lucide-react';
import toast from 'react-hot-toast';

interface FileItem {
  id: number;
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
  owner: string;
  created_at: string;
  updated_at: string;
  mount_id?: string;  // Changed from number to string
}

interface Mountpoint {
  id: string;  // Changed from number to string to match API
  name: string;
  mount_path: string;
  raid_level: string;
  total_size: number;
  used_size: number;
}

const FileExplorer: React.FC = () => {
  const [mountpoints, setMountpoints] = useState<Mountpoint[]>([]);
  const [selectedMount, setSelectedMount] = useState<Mountpoint | null>(null);
  const [currentPath, setCurrentPath] = useState('/');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);

  // Load mountpoints on component mount
  useEffect(() => {
    loadMountpoints();
  }, []);

  // Load files when mount or path changes
  useEffect(() => {
    if (selectedMount) {
      loadFiles();
    }
  }, [selectedMount, currentPath]);

  const loadMountpoints = async () => {
    try {
      setLoading(true);
      console.log('[FileExplorer] Loading mountpoints...');
      const response = await window.electronAPI.invoke('get_mountpoints', {});
      console.log('[FileExplorer] Mountpoints response:', response);
      
      if (response.success && response.mountpoints) {
        setMountpoints(response.mountpoints);
        if (response.mountpoints.length > 0 && !selectedMount) {
          setSelectedMount(response.mountpoints[0]);
        }
      } else {
        console.error('[FileExplorer] Failed to load mountpoints:', response);
        setError('Failed to load storage drives');
      }
    } catch (err) {
      console.error('[FileExplorer] Error loading mountpoints:', err);
      setError(err instanceof Error ? err.message : 'Failed to load storage drives');
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async () => {
    if (!selectedMount) return;

    try {
      setLoading(true);
      setError(null);
      const response = await window.electronAPI.invoke('list_files', {
        path: currentPath,
        mountId: selectedMount.id
      });

      if (response.success && response.files) {
        setFiles(response.files);
      } else {
        setError('Failed to load files');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const navigateToFolder = (folder: FileItem) => {
    if (folder.type === 'directory') {
      setCurrentPath(folder.path);
    }
  };

  const navigateUp = () => {
    if (currentPath === '/') return;
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    setCurrentPath('/' + parts.join('/'));
  };

  const formatSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getBreadcrumbs = () => {
    const parts = currentPath.split('/').filter(Boolean);
    const breadcrumbs = [{ name: 'Root', path: '/' }];
    
    let path = '';
    for (const part of parts) {
      path += '/' + part;
      breadcrumbs.push({ name: part, path });
    }
    
    return breadcrumbs;
  };

  const handleCreateFolder = async () => {
    const name = prompt('Enter folder name:');
    if (!name || !selectedMount) return;

    try {
      const response = await window.electronAPI.invoke('create_folder', {
        path: currentPath,
        name,
        mountId: selectedMount.id
      });

      if (response.success) {
        loadFiles();
      } else {
        alert('Failed to create folder');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create folder');
    }
  };

  const handleDelete = async (file: FileItem) => {
    if (!confirm(`Delete ${file.name}?`)) return;

    try {
      const response = await window.electronAPI.invoke('delete_file', {
        fileId: file.id
      });

      if (response.success) {
        loadFiles();
      } else {
        alert('Failed to delete file');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete file');
    }
  };

  const handleRename = async (file: FileItem) => {
    const newName = prompt('Enter new name:', file.name);
    if (!newName) return;

    try {
      const response = await window.electronAPI.invoke('rename_file', {
        fileId: file.id,
        newName
      });

      if (response.success) {
        loadFiles();
      } else {
        alert('Failed to rename file');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to rename file');
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-800">File Explorer</h1>
          <button
            onClick={loadFiles}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Storage Selector */}
      <div className="bg-white border-b px-6 py-3">
        <div className="flex items-center gap-4">
          <HardDrive className="w-5 h-5 text-gray-600" />
          <select
            value={selectedMount?.id || ''}
            onChange={(e) => {
              const mount = mountpoints.find(m => m.id === e.target.value);
              setSelectedMount(mount || null);
              setCurrentPath('/');
            }}
            className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          >
            {mountpoints.map(mount => (
              <option key={mount.id} value={mount.id}>
                {mount.name} ({mount.raid_level}) - {formatSize(mount.used_size)} / {formatSize(mount.total_size)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action Bar */}
      <div className="bg-white border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={handleCreateFolder}
            className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
            disabled={!selectedMount}
          >
            <FolderPlus className="w-4 h-4" />
            New Folder
          </button>
          <button
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            disabled={!selectedMount}
          >
            <Upload className="w-4 h-4" />
            Upload
          </button>
        </div>
      </div>

      {/* Breadcrumb Navigation */}
      <div className="bg-white border-b px-6 py-3">
        <div className="flex items-center gap-2 text-sm">
          {getBreadcrumbs().map((crumb, index) => (
            <div key={crumb.path} className="flex items-center gap-2">
              {index > 0 && <ChevronRight className="w-4 h-4 text-gray-400" />}
              <button
                onClick={() => setCurrentPath(crumb.path)}
                className="text-blue-600 hover:text-blue-800 hover:underline"
              >
                {crumb.name}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* File List */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4 backdrop-blur-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-white/5 border-b border-white/10">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Owner
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Modified
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {currentPath !== '/' && (
                  <tr className="hover:bg-white/10 cursor-pointer transition-colors" onClick={navigateUp}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <Folder className="w-5 h-5 text-blue-400" />
                        <span className="font-medium text-white">..</span>
                      </div>
                    </td>
                    <td colSpan={4}></td>
                  </tr>
                )}
                {files.map((file, idx) => (
                  <tr
                    key={`${currentPath}/${file.path}-${idx}`}
                    className={`hover:bg-gray-50 transition-colors ${selectedFile?.path === file.path ? 'bg-blue-50' : ''}`}
                    onClick={() => setSelectedFile(file)}
                    onDoubleClick={() => file.type === 'directory' && navigateToFolder(file)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {file.type === 'directory' ? (
                          <Folder className="w-5 h-5 text-blue-600 fill-blue-100" />
                        ) : (
                          <File className="w-5 h-5 text-gray-600" />
                        )}
                        <span className="font-medium text-gray-900">{file.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {file.type === 'file' ? formatSize(file.size) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {file.owner || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {file.updated_at ? formatDate(file.updated_at) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRename(file);
                          }}
                          className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          title="Rename"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        {file.type === 'file' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toast('Download feature coming soon', { icon: '📥' });
                            }}
                            className="p-1.5 text-green-600 hover:bg-green-50 rounded transition-colors"
                            title="Download"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(file);
                          }}
                          className="p-1.5 text-red-600 hover:bg-red-50 rounded transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {files.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center gap-2 text-gray-400">
                        <Folder className="w-12 h-12" />
                        <span className="text-sm">This folder is empty</span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileExplorer;
