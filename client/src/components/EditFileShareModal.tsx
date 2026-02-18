import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import toast from 'react-hot-toast';
import { updateFileShare, type FileShare, type UpdateFileShareRequest } from '../api/shares';

interface EditFileShareModalProps {
  fileShare: FileShare;
  onClose: () => void;
  onSuccess: () => void;
}

export default function EditFileShareModal({ fileShare, onClose, onSuccess }: EditFileShareModalProps) {
  const { t } = useTranslation(['shares', 'common']);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<UpdateFileShareRequest>({
    can_read: fileShare.can_read,
    can_write: fileShare.can_write,
    can_delete: fileShare.can_delete,
    can_share: fileShare.can_share,
    expires_at: fileShare.expires_at ? fileShare.expires_at.split('T')[0] : null
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await updateFileShare(fileShare.id, {
        ...formData,
        expires_at: formData.expires_at ? `${formData.expires_at}T23:59:59` : null
      });
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
          <h2 className="text-xl font-semibold text-white">{t('shares:modal.editFileShare')}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File and User Info (read-only) */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">{t('shares:form.file')}</label>
              <div className="px-3 py-2 bg-slate-800/50 text-slate-300 rounded-lg">
                {fileShare.file_name}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">{t('shares:form.sharedWith')}</label>
              <div className="px-3 py-2 bg-slate-800/50 text-slate-300 rounded-lg">
                {fileShare.shared_with_username}
              </div>
            </div>
          </div>

          {/* Permissions */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">{t('shares:table.permissions')}</label>
            <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50 space-y-2">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_read}
                  onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.canRead')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_write}
                  onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.canWrite')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_delete}
                  onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.canDelete')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_share}
                  onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-slate-300">{t('shares:permissions.canShare')}</span>
              </label>
            </div>
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
