import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import toast from 'react-hot-toast';
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
    } catch (error: unknown) {
      toast.error(t('shares:toast.createShareFailed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">{t('shares:modal.shareWithUser')}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
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
                <span className="text-xs text-slate-400">{explorerPath}</span>
                <button
                  type="button"
                  className="text-xs text-sky-400 hover:underline"
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
                className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 mb-2"
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
                    <option key={file.id} value={file.id} disabled className="text-slate-500 bg-slate-900">
                      📁 {file.name}
                    </option>
                  ) : (
                    <option key={file.id} value={file.id} className="text-white bg-slate-800">
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
              <label className="block text-sm font-medium text-slate-300 mb-1">{t('shares:modal.shareWithUser')}</label>
              <select
                value={formData.shared_with_user_id}
                onChange={(e) => setFormData({ ...formData, shared_with_user_id: Number(e.target.value) })}
                className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
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
              <label className="block text-sm font-medium text-slate-300 mb-2">{t('shares:table.permissions')}</label>
              <div className={`bg-slate-800/30 rounded-lg p-3 border border-slate-700/50 space-y-2 ${formData.shared_with_user_id === 0 ? 'opacity-50 pointer-events-none' : ''}`}>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_read}
                    onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">{t('shares:permissions.canRead')} ({t('shares:permissions.canReadDesc')})</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_write}
                    onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">{t('shares:permissions.canWrite')} ({t('shares:permissions.canWriteDesc')})</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_delete}
                    onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">{t('shares:permissions.canDelete')}</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_share}
                    onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">{t('shares:permissions.canShare')} ({t('shares:permissions.canShareDesc')})</span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                {t('shares:form.expirationDateOptional')}
              </label>
              <input
                type="datetime-local"
                value={formData.expires_at || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  expires_at: e.target.value || null
                })}
                className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-slate-300 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-700/50 transition-colors"
              >
                {t('shares:buttons.cancel')}
              </button>
              <button
                type="submit"
                disabled={loading || formData.file_id === 0 || formData.shared_with_user_id === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 touch-manipulation active:scale-95 transition-all"
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
