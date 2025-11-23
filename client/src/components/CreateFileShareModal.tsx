import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { createFileShare, type CreateFileShareRequest } from '../api/shares';
import { apiClient } from '../lib/api';

interface CreateFileShareModalProps {
  fileId?: number;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateFileShareModal({ fileId, onClose, onSuccess }: CreateFileShareModalProps) {
  const [files, setFiles] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [formData, setFormData] = useState<CreateFileShareRequest>({
    file_id: fileId || 0,
    shared_with_user_id: 0,
    can_read: true,
    can_write: false,
    can_delete: false,
    can_share: false,
    expires_at: null
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const usersResponse = await apiClient.get('/users');
      setUsers(usersResponse.data);
      
      if (!fileId) {
        const filesResponse = await apiClient.get('/files/list', { params: { path: '/' } });
        setFiles(filesResponse.data.files || []);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await createFileShare({
        ...formData,
        expires_at: formData.expires_at || null
      });
      onSuccess();
    } catch (error: any) {
      console.error('Failed to create file share:', error);
      alert(error.response?.data?.detail || 'Failed to create file share');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Share with User</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {loadingData ? (
          <div className="text-center py-8">Loading...</div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* File Selection */}
            {!fileId && (
              <div>
                <label className="block text-sm font-medium mb-1">File</label>
                <select
                  value={formData.file_id}
                  onChange={(e) => setFormData({ ...formData, file_id: Number(e.target.value) })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  required
                >
                  <option value={0}>Select a file...</option>
                  {files.filter(f => !f.is_directory).map((file) => (
                    <option key={file.id} value={file.id}>
                      {file.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* User Selection */}
            <div>
              <label className="block text-sm font-medium mb-1">Share with User</label>
              <select
                value={formData.shared_with_user_id}
                onChange={(e) => setFormData({ ...formData, shared_with_user_id: Number(e.target.value) })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                required
              >
                <option value={0}>Select a user...</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.username} ({user.email || 'no email'})
                  </option>
                ))}
              </select>
            </div>

            {/* Permissions */}
            <div>
              <label className="block text-sm font-medium mb-2">Permissions</label>
              <div className="space-y-2 pl-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_read}
                    onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Can Read (view and download)</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_write}
                    onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Can Write (edit file)</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_delete}
                    onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Can Delete</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_share}
                    onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Can Share (re-share with others)</span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-sm font-medium mb-1">
                Expiration Date (Optional)
              </label>
              <input
                type="datetime-local"
                value={formData.expires_at || ''}
                onChange={(e) => setFormData({ 
                  ...formData, 
                  expires_at: e.target.value || null 
                })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || formData.file_id === 0 || formData.shared_with_user_id === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Sharing...' : 'Share File'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
