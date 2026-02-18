import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import toast from 'react-hot-toast';
import { updateShareLink, type ShareLink, type UpdateShareLinkRequest } from '../api/shares';

interface EditShareLinkModalProps {
  shareLink: ShareLink;
  onClose: () => void;
  onSuccess: () => void;
}

export default function EditShareLinkModal({ shareLink, onClose, onSuccess }: EditShareLinkModalProps) {
  const { t } = useTranslation(['shares', 'common']);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<UpdateShareLinkRequest>({
    password: '',
    allow_download: shareLink.allow_download,
    allow_preview: shareLink.allow_preview,
    max_downloads: shareLink.max_downloads,
    expires_at: shareLink.expires_at ? shareLink.expires_at.split('T')[0] : null,
    description: shareLink.description || ''
  });
  const [changePassword, setChangePassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const updateData: UpdateShareLinkRequest = {
        allow_download: formData.allow_download,
        allow_preview: formData.allow_preview,
        max_downloads: formData.max_downloads || null,
        expires_at: formData.expires_at ? `${formData.expires_at}T23:59:59` : null,
        description: formData.description || undefined
      };

      // Only include password if user wants to change it
      if (changePassword) {
        updateData.password = formData.password || ''; // Empty string removes password
      }

      await updateShareLink(shareLink.id, updateData);
      onSuccess();
    } catch (error: unknown) {
      toast.error(t('shares:toast.updateFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">{t('shares:modal.editShareLink')}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Info (read-only) */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">{t('shares:form.file')}</label>
            <div className="px-3 py-2 bg-slate-800/50 text-slate-300 rounded-lg">
              {shareLink.file_name}
            </div>
          </div>

          {/* Password */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-slate-300">{t('shares:form.passwordProtection')}</label>
              <label className="flex items-center text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={changePassword}
                  onChange={(e) => setChangePassword(e.target.checked)}
                  className="mr-2"
                />
                {t('shares:buttons.changePassword')}
              </label>
            </div>
            {shareLink.has_password && !changePassword && (
              <div className="text-sm px-3 py-2 bg-sky-500/10 border border-sky-500/30 text-sky-300 rounded-lg">
                🔒 {t('shares:form.currentlyProtected')}
              </div>
            )}
            {changePassword && (
              <>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder={t('shares:form.passwordRemoveHint')}
                  className="w-full px-3 py-2 bg-slate-800/60 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
                <p className="text-xs text-slate-500 mt-1">
                  {t('shares:form.passwordRemoveHint')}
                </p>
              </>
            )}
          </div>

          {/* Permissions */}
          <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50">
            <div className="grid grid-cols-2 gap-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.allow_download}
                  onChange={(e) => setFormData({ ...formData, allow_download: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.allowDownload')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.allow_preview}
                  onChange={(e) => setFormData({ ...formData, allow_preview: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.allowPreview')}</span>
              </label>
            </div>
          </div>

          {/* Max Downloads */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {t('shares:form.maxDownloads')} ({t('shares:form.maxDownloadsHint')})
            </label>
            <input
              type="number"
              min="1"
              value={formData.max_downloads || ''}
              onChange={(e) => setFormData({ ...formData, max_downloads: e.target.value ? Number(e.target.value) : null })}
              placeholder={t('shares:form.unlimited')}
              className="w-full px-3 py-2 bg-slate-800/60 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
            <p className="text-xs text-slate-500 mt-1">
              {t('shares:form.currentDownloads', { count: shareLink.download_count })}
            </p>
          </div>

          {/* Expiration Date */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {t('shares:form.expirationDate')} ({t('shares:form.expirationHint')})
            </label>
            <input
              type="date"
              value={formData.expires_at || ''}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value || null })}
              min={new Date().toISOString().split('T')[0]}
              className="w-full px-3 py-2 bg-slate-800/60 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">{t('shares:form.descriptionOptional')}</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder={t('shares:form.descriptionPlaceholder')}
              rows={3}
              maxLength={500}
              className="w-full px-3 py-2 bg-slate-800/60 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end space-x-2 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-300 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-700/50 transition-colors"
            >
              {t('shares:buttons.cancel')}
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 touch-manipulation active:scale-95 transition-all"
            >
              {loading ? t('shares:buttons.saving') : t('shares:buttons.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
