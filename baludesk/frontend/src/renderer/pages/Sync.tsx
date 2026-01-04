import { useEffect, useState } from 'react';
import { FolderSync, FolderPlus, Trash2, Settings, CheckCircle, Circle } from 'lucide-react';
import toast from 'react-hot-toast';
import { formatSize } from '../../lib/formatters';
import { BackendMessage, BackendResponse } from '../../lib/types';

// Type assertion for Electron API
declare const window: any;

interface SyncFolder {
  id: string;
  localPath: string;
  remotePath: string;
  enabled: boolean;
  status?: string;  // Add status from backend
  size?: number;  // Folder size in bytes
}

export default function Sync() {
  const [folders, setFolders] = useState<SyncFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<SyncFolder | null>(null);
  const [conflictResolution, setConflictResolution] = useState('ask');

  useEffect(() => {
    // Listen to backend messages
    window.electronAPI.onBackendMessage((message: BackendMessage) => {
      if (message.type === 'sync_folders') {
        setFolders(message.data);
      }
    });

    // Request initial data
    fetchSyncFolders();

    return () => {
      window.electronAPI.removeBackendListener();
    };
  }, []);

  const fetchSyncFolders = async () => {
    setLoading(true);
    try {
      const response: BackendResponse = await window.electronAPI.sendBackendCommand({
        type: 'get_folders',
      });
      if (response.success || response.folders) {
        // Backend returns folders array directly or in response.folders
        const folderData = response.folders || response.data || [];
        // Transform backend response (snake_case) to match TypeScript interface (camelCase)
        const transformedFolders = folderData.map((folder: any) => ({
          id: folder.id,
          localPath: folder.local_path,
          remotePath: folder.remote_path,
          enabled: folder.enabled,
          status: folder.status,  // Add status from backend
          size: folder.size  // Add size from backend in bytes
        }));
        setFolders(transformedFolders);
      }
    } catch (err) {
      console.error('Failed to fetch sync folders:', err);
      toast.error('Failed to load sync folders');
    } finally {
      setLoading(false);
    }
  };

  const handleAddFolder = async () => {
    try {
      const localPath = await window.electronAPI.selectFolder({
        defaultPath: '', // No default path in browser context
      });

      if (localPath) {
        // TODO: Get remote path from user (maybe a dialog)
        const remotePath = `/synced/${localPath.split('\\').pop() || 'folder'}`;

        const response: BackendResponse = await window.electronAPI.sendBackendCommand({
          type: 'add_sync_folder',
          payload: {
            local_path: localPath,
            remote_path: remotePath,
          }
        });

        if (response.success) {
          toast.success('Folder added successfully');
          fetchSyncFolders();
        } else {
          toast.error(response.error || 'Failed to add folder');
        }
      }
    } catch (err) {
      console.error('Error adding folder:', err);
      toast.error('Error adding folder');
    }
  };

  const handleToggleFolder = async (folderId: string, enabled: boolean) => {
    try {
      // Send pause or resume based on current state
      const commandType = enabled ? 'pause_sync' : 'resume_sync';
      const response = await window.electronAPI.sendBackendCommand({
        type: commandType,
        payload: {
          folder_id: folderId,
        }
      });

      if (response.success) {
        toast.success(`Sync ${!enabled ? 'resumed' : 'paused'}`);
        fetchSyncFolders();
      } else {
        toast.error(response.error || 'Failed to update folder');
      }
    } catch (err) {
      console.error('Error toggling folder:', err);
      toast.error('Error toggling folder');
    }
  };

  const openFolderSettings = (folder: SyncFolder) => {
    setSelectedFolder(folder);
    setConflictResolution('ask'); // Default
    setShowSettingsModal(true);
  };

  const handleSaveFolderSettings = async () => {
    if (!selectedFolder) return;

    try {
        const response: BackendResponse = await window.electronAPI.sendBackendCommand({
        type: 'update_sync_folder',
        payload: {
          folder_id: selectedFolder.id,
          conflict_resolution: conflictResolution
        }
      });

      if (response.success) {
        toast.success('Folder settings saved');
        setShowSettingsModal(false);
        fetchSyncFolders();
      } else {
        toast.error(response.error || 'Failed to save folder settings');
      }
    } catch (err) {
      console.error('Error saving folder settings:', err);
      toast.error('Error saving folder settings');
    }
  };

  const handleRemoveFolder = async (folderId: string) => {
    if (confirm('Are you sure you want to remove this sync folder?')) {
      try {
      const response: BackendResponse = await window.electronAPI.sendBackendCommand({
          type: 'remove_sync_folder',
          payload: {
            folder_id: folderId,
          }
        });

        if (response.success) {
          toast.success('Folder removed');
          fetchSyncFolders();
        } else {
          toast.error(response.error || 'Failed to remove folder');
        }
      } catch (err) {
        console.error('Error removing folder:', err);
        toast.error('Error removing folder');
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center space-x-3">
            <div className="rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 p-3">
              <FolderSync className="h-6 w-6 text-white" />
            </div>
            <span>Sync Folders</span>
          </h1>
          <p className="mt-2 text-slate-400">Manage folders to synchronize with your server</p>
        </div>
        <button
          onClick={handleAddFolder}
          disabled={loading}
          className="flex items-center space-x-2 rounded-lg bg-gradient-to-r from-blue-500 to-blue-600 px-6 py-3 font-medium text-white shadow-lg shadow-blue-500/30 transition-all hover:shadow-xl hover:shadow-blue-500/40 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <FolderPlus className="h-5 w-5" />
          <span>Add Folder</span>
        </button>
      </div>

      {/* Folders List */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 backdrop-blur-sm">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="text-slate-400">Loading folders...</div>
          </div>
        ) : folders.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/50 py-12 text-center">
            <FolderSync className="mx-auto h-12 w-12 text-slate-600" />
            <p className="mt-4 text-slate-400 text-lg font-medium">No sync folders configured</p>
            <p className="mt-2 text-sm text-slate-500">Click "Add Folder" to start syncing files</p>
          </div>
        ) : (
          <div className="space-y-3">
            {folders.map((folder) => (
              <div
                key={folder.id}
                className="group rounded-lg border border-slate-800 bg-slate-950/50 p-4 transition-all hover:border-slate-700 hover:bg-slate-950"
              >
                <div className="flex items-center justify-between">
                  {/* Left side: Folder info */}
                  <div className="flex items-center space-x-4 flex-1">
                    <button
                      onClick={() => handleToggleFolder(folder.id, folder.status !== 'paused')}
                      className="flex-shrink-0 text-slate-400 hover:text-slate-200 transition-colors"
                    >
                      {folder.status === 'paused' ? (
                        <Circle className="h-6 w-6" />
                      ) : (
                        <CheckCircle className="h-6 w-6 text-green-500" />
                      )}
                    </button>

                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-white break-all">
                        📁 {folder.localPath}
                      </p>
                      <p className="text-sm text-slate-400 mt-1 break-all">
                        ☁️ Syncs to: {folder.remotePath}
                      </p>
                      <p className="text-xs text-slate-500 mt-2">
                        📊 Size: {formatSize(folder.size)}
                      </p>
                    </div>
                  </div>

                  {/* Right side: Status badge & Actions */}
                  <div className="flex items-center space-x-3 flex-shrink-0">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                        folder.status !== 'paused'
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {folder.status === 'paused' ? 'Paused' : 'Active'}
                    </span>

                    <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => openFolderSettings(folder)}
                        className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                        title="Settings"
                      >
                        <Settings className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleRemoveFolder(folder.id)}
                        className="rounded-lg p-2 text-slate-400 hover:bg-red-500/20 hover:text-red-400 transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
        <p className="text-sm text-slate-400">
          <span className="font-medium text-slate-300">💡 Tip:</span> Only active folders will be synced. Click the circle icon to pause/resume sync for a folder.
        </p>
      </div>

      {/* Folder Settings Modal */}
      {showSettingsModal && selectedFolder && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 rounded-xl border border-slate-800 w-full max-w-md shadow-xl">
            {/* Header */}
            <div className="border-b border-slate-800 p-6">
              <h2 className="text-xl font-bold text-white">Folder Settings</h2>
              <p className="mt-2 text-sm text-slate-400">{selectedFolder.remotePath}</p>
            </div>

            {/* Content */}
            <div className="p-6 space-y-6">
              {/* Conflict Resolution */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Conflict Resolution
                </label>
                <select
                  value={conflictResolution}
                  onChange={(e) => setConflictResolution(e.target.value)}
                  className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-white hover:border-slate-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
                >
                  <option value="ask">Ask (recommended)</option>
                  <option value="skip">Skip conflicting files</option>
                  <option value="overwrite_local">Overwrite local version</option>
                  <option value="overwrite_remote">Overwrite remote version</option>
                </select>
                <p className="mt-2 text-xs text-slate-500">
                  Choose what to do when the same file is modified in both locations.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="border-t border-slate-800 p-6 flex items-center justify-end space-x-3">
              <button
                onClick={() => setShowSettingsModal(false)}
                className="rounded-lg px-4 py-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveFolderSettings}
                className="rounded-lg bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-2 text-white font-medium hover:shadow-lg hover:shadow-blue-500/30 transition-all"
              >
                Save Settings
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
