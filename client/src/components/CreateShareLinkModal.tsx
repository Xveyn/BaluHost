import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { createShareLink, type CreateShareLinkRequest } from '../api/shares';
import { apiClient } from '../lib/api';

interface CreateShareLinkModalProps {
  fileId?: number;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateShareLinkModal({ fileId, onClose, onSuccess }: CreateShareLinkModalProps) {
  const { t } = useTranslation(['shares', 'common']);
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(!fileId);
  const [formData, setFormData] = useState<CreateShareLinkRequest>({
    file_id: fileId || 0,
    password: '',
    allow_download: true,
    allow_preview: true,
    max_downloads: null,
    expires_at: null,
    description: ''
  });

  useEffect(() => {
    if (!fileId) {
      loadFiles();
    }
  }, [fileId]);

  const loadFiles = async () => {
    try {
      const response = await apiClient.get('/files/list', { params: { path: '/' } });
      setFiles(response.data.files || []);
    } catch (error) {
      console.error('Failed to load files:', error);
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await createShareLink({
        ...formData,
        password: formData.password || undefined,
        expires_at: formData.expires_at || null
      });
      onSuccess();
    } catch (error: any) {
      console.error('Failed to create share link:', error);
      alert(error.response?.data?.detail || 'Failed to create share link');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-gray-900/95 backdrop-blur-md border border-white/10 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white">{t('shares:modal.createShareLink')}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200 transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Selection */}
          {!fileId && (
            <div>
              <label className="block text-sm font-semibold text-gray-300 mb-2">{t('shares:form.file')}</label>
              {loadingFiles ? (
                <div className="text-gray-400">{t('shares:loadingFiles')}</div>
              ) : (
                <select
                  value={formData.file_id}
                  onChange={(e) => setFormData({ ...formData, file_id: Number(e.target.value) })}
                  className="w-full px-4 py-2.5 bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white"
                  required
                >
                  <option value={0} className="bg-gray-800">{t('shares:form.selectFile')}</option>
                  {files.filter(f => !f.is_directory).map((file) => (
                    <option key={file.id} value={file.id} className="bg-gray-800">
                      {file.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2">
              {t('shares:form.passwordProtectionOptional')}
            </label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="w-full px-4 py-2.5 bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white placeholder-gray-400"
              placeholder={t('shares:form.passwordPlaceholder')}
            />
          </div>

          {/* Max Downloads */}
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2">
              {t('shares:form.maxDownloadsOptional')}
            </label>
            <input
              type="number"
              min="1"
              value={formData.max_downloads || ''}
              onChange={(e) => setFormData({ 
                ...formData, 
                max_downloads: e.target.value ? Number(e.target.value) : null 
              })}
              className="w-full px-4 py-2.5 bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white placeholder-gray-400"
              placeholder={t('shares:form.unlimited')}
            />
          </div>

          {/* Expiration Date */}
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2">
              {t('shares:form.expirationDateOptional')}
            </label>
            <input
              type="datetime-local"
              value={formData.expires_at || ''}
              onChange={(e) => setFormData({ 
                ...formData, 
                expires_at: e.target.value || null 
              })}
              className="w-full px-4 py-2.5 bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-2">
              {t('shares:form.descriptionOptional')}
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-4 py-2.5 bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white placeholder-gray-400 resize-none"
              rows={3}
              placeholder={t('shares:form.descriptionPlaceholderLink')}
            />
          </div>

          {/* Checkboxes */}
          <div className="space-y-3 bg-white/5 p-4 rounded-lg border border-white/10">
            <label className="flex items-center cursor-pointer group">
              <input
                type="checkbox"
                checked={formData.allow_download}
                onChange={(e) => setFormData({ ...formData, allow_download: e.target.checked })}
                className="mr-3 w-4 h-4 text-blue-500 rounded focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">{t('shares:permissions.allowDownloads')}</span>
            </label>
            <label className="flex items-center cursor-pointer group">
              <input
                type="checkbox"
                checked={formData.allow_preview}
                onChange={(e) => setFormData({ ...formData, allow_preview: e.target.checked })}
                className="mr-3 w-4 h-4 text-blue-500 rounded focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">{t('shares:permissions.allowPreviews')}</span>
            </label>
          </div>

          {/* Buttons */}
          <div className="flex justify-end space-x-3 pt-6 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 text-gray-300 bg-white/5 border border-white/10 rounded-lg hover:bg-white/10 transition-all font-medium"
            >
              {t('shares:buttons.cancel')}
            </button>
            <button
              type="submit"
              disabled={loading || formData.file_id === 0}
              className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium shadow-lg"
            >
              {loading ? t('shares:buttons.creating') : t('shares:modal.createShareLink')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
