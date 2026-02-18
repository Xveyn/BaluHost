import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import toast from 'react-hot-toast';
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
    } catch {
      // Non-critical: file list will remain empty
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
    } catch (error: unknown) {
      toast.error(t('shares:toast.createLinkFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-white">{t('shares:modal.createShareLink')}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Selection */}
          {!fileId && (
            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-2">{t('shares:form.file')}</label>
              {loadingFiles ? (
                <div className="text-slate-400">{t('shares:loadingFiles')}</div>
              ) : (
                <select
                  value={formData.file_id}
                  onChange={(e) => setFormData({ ...formData, file_id: Number(e.target.value) })}
                  className="w-full px-4 py-2.5 bg-slate-800/60 border border-slate-700 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-white"
                  required
                >
                  <option value={0} className="bg-slate-800">{t('shares:form.selectFile')}</option>
                  {files.filter(f => !f.is_directory).map((file) => (
                    <option key={file.id} value={file.id} className="bg-slate-800">
                      {file.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">
              {t('shares:form.passwordProtectionOptional')}
            </label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="w-full px-4 py-2.5 bg-slate-800/60 border border-slate-700 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-white placeholder-slate-500"
              placeholder={t('shares:form.passwordPlaceholder')}
            />
          </div>

          {/* Max Downloads */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">
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
              className="w-full px-4 py-2.5 bg-slate-800/60 border border-slate-700 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-white placeholder-slate-500"
              placeholder={t('shares:form.unlimited')}
            />
          </div>

          {/* Expiration Date */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">
              {t('shares:form.expirationDateOptional')}
            </label>
            <input
              type="datetime-local"
              value={formData.expires_at || ''}
              onChange={(e) => setFormData({
                ...formData,
                expires_at: e.target.value || null
              })}
              className="w-full px-4 py-2.5 bg-slate-800/60 border border-slate-700 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-white"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">
              {t('shares:form.descriptionOptional')}
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-4 py-2.5 bg-slate-800/60 border border-slate-700 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-white placeholder-slate-500 resize-none"
              rows={3}
              placeholder={t('shares:form.descriptionPlaceholderLink')}
            />
          </div>

          {/* Checkboxes */}
          <div className="space-y-3 bg-slate-800/30 p-4 rounded-lg border border-slate-700/50">
            <label className="flex items-center cursor-pointer group">
              <input
                type="checkbox"
                checked={formData.allow_download}
                onChange={(e) => setFormData({ ...formData, allow_download: e.target.checked })}
                className="mr-3 w-4 h-4 text-blue-500 rounded focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{t('shares:permissions.allowDownloads')}</span>
            </label>
            <label className="flex items-center cursor-pointer group">
              <input
                type="checkbox"
                checked={formData.allow_preview}
                onChange={(e) => setFormData({ ...formData, allow_preview: e.target.checked })}
                className="mr-3 w-4 h-4 text-blue-500 rounded focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{t('shares:permissions.allowPreviews')}</span>
            </label>
          </div>

          {/* Buttons */}
          <div className="flex justify-end space-x-3 pt-6 border-t border-slate-700/50">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 text-slate-300 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-700/50 transition-all font-medium"
            >
              {t('shares:buttons.cancel')}
            </button>
            <button
              type="submit"
              disabled={loading || formData.file_id === 0}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium touch-manipulation active:scale-95"
            >
              {loading ? t('shares:buttons.creating') : t('shares:modal.createShareLink')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
