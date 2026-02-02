import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { createFileShare, type CreateFileShareRequest } from '../api/shares';
import { apiClient } from '../lib/api';


interface CreateFileShareModalProps {
  fileId?: number;
  users: any[];
  onClose: () => void;
  onSuccess: () => void;
}

const CreateFileShareModal = ({ fileId, users, onClose, onSuccess }: CreateFileShareModalProps) => {
  const { t } = useTranslation(['shares', 'common']);
  const [loading, setLoading] = useState(false);
  const [, setExplorerLoading] = useState(false);
  const [explorerPath, setExplorerPath] = useState<string>('/');
  const [explorerFiles, setExplorerFiles] = useState<any[]>([]);
  const [formData, setFormData] = useState<CreateFileShareRequest>({
    file_id: fileId || 0,
    shared_with_user_id: 0,
    can_read: true,
    can_write: false,
    can_delete: false,
    can_share: false,
    expires_at: null
  });

  // Load files for explorer
  useEffect(() => {
    if (!fileId) {
      fetchFiles(explorerPath);
    }
  }, [explorerPath, fileId]);

  const fetchFiles = async (path: string) => {
    setExplorerLoading(true);
    try {
      const response = await apiClient.get('/files/list', { params: { path } });
      setExplorerFiles(response.data.files || []);
    } catch (err) {
      setExplorerFiles([]);
    } finally {
      setExplorerLoading(false);
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
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto border border-gray-800 shadow-2xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-white">{t('shares:modal.shareWithUser')}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Explorer Selection */}
          {!fileId && (
            <div>
              <label className="block text-sm font-medium mb-1 text-white">{t('shares:form.selectFileToShare')}</label>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-gray-400">{explorerPath}</span>
                <button
                  type="button"
                  className="text-xs text-blue-400 hover:underline"
                  disabled={explorerPath === '/'}
                  onClick={() => {
                    const parts = explorerPath.split('/').filter(Boolean);
                    const newPath = '/' + parts.slice(0, -1).join('/') + (parts.length > 1 ? '/' : '');
                    setExplorerPath(newPath);
                  }}
                >
                  ↑ {t('shares:buttons.up')}
                </button>
              </div>
              <select
                className="w-full px-3 py-2 border border-gray-700 bg-gray-800 text-white rounded-lg focus:ring-2 focus:ring-blue-500 mb-2"
                value={formData.file_id}
                onChange={e => {
                  const selectedId = Number(e.target.value);
                  const selected = explorerFiles.find(f => f.id === selectedId);
                  if (selected && selected.is_directory) {
                    // Navigate into folder, reset file selection
                    let newPath = explorerPath;
                    if (!newPath.endsWith('/')) newPath += '/';
                    newPath += selected.name + '/';
                    setExplorerPath(newPath.replace(/\\/g, '/'));
                    setFormData({ ...formData, file_id: 0 });
                  } else {
                    setFormData({ ...formData, file_id: selectedId });
                  }
                }}
                required
              >
                <option value={0}>{t('shares:form.selectFile')}</option>
                {explorerFiles.map((file: any) => (
                  file.is_directory ? (
                    <option key={file.id} value={file.id} disabled className="text-gray-500 bg-gray-900">
                      📁 {file.name}
                    </option>
                  ) : (
                    <option key={file.id} value={file.id} className="text-white bg-gray-800">
                      📄 {file.name}
                    </option>
                  )
                ))}
              </select>
              {formData.file_id === 0 && (
                <div className="text-xs text-red-400 mb-2">{t('shares:form.selectFileRequired')}</div>
              )}
            </div>
          )}

            {/* User Selection */}
            <div>
              <label className="block text-sm font-medium mb-1">{t('shares:modal.shareWithUser')}</label>
              <select
                value={formData.shared_with_user_id}
                onChange={(e) => setFormData({ ...formData, shared_with_user_id: Number(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-700 bg-gray-800 text-white rounded-lg focus:ring-2 focus:ring-blue-500"
                required
                disabled={users.length === 0}
              >
                <option value={0} disabled>{t('shares:form.selectUser')}</option>
                {(users ?? []).map((user) => (
                  <option key={user.id || user._id || user.email} value={user.id || user._id || ''}>
                    {user.username || user.name || user.email || 'Unknown User'}
                  </option>
                ))}
              </select>
            </div>

            {/* Permissions */}
            <div>
              <label className="block text-sm font-medium mb-2 text-white">{t('shares:table.permissions')}</label>
              <div className={`space-y-2 pl-4 ${formData.shared_with_user_id === 0 ? 'opacity-50 pointer-events-none' : ''}`}>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_read}
                    onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm">{t('shares:permissions.canRead')} ({t('shares:permissions.canReadDesc')})</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_write}
                    onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm">{t('shares:permissions.canWrite')} ({t('shares:permissions.canWriteDesc')})</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_delete}
                    onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm">{t('shares:permissions.canDelete')}</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_share}
                    onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm">{t('shares:permissions.canShare')} ({t('shares:permissions.canShareDesc')})</span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-sm font-medium mb-1">
                <span className="text-white">{t('shares:form.expirationDateOptional')}</span>
              </label>
              <input
                type="datetime-local"
                value={formData.expires_at || ''}
                onChange={(e) => setFormData({ 
                  ...formData, 
                  expires_at: e.target.value || null 
                })}
                className="w-full px-3 py-2 border border-gray-700 bg-gray-800 text-white rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-gray-300 bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700"
              >
                {t('shares:buttons.cancel')}
              </button>
              <button
                type="submit"
                disabled={loading || formData.file_id === 0 || formData.shared_with_user_id === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 border border-blue-700"
              >
                {loading ? t('shares:buttons.sharing') : t('shares:buttons.share')}
              </button>
            </div>
          </form>
      </div>
    </div>
  );
}

export default CreateFileShareModal;
