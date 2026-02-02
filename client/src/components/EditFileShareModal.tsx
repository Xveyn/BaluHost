import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
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
    } catch (error: any) {
      console.error('Failed to update file share:', error);
      alert(error.response?.data?.detail || 'Failed to update file share');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">{t('shares:modal.editFileShare')}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File and User Info (read-only) */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">{t('shares:form.file')}</label>
              <div className="px-3 py-2 bg-gray-50 rounded-lg text-gray-700">
                {fileShare.file_name}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('shares:form.sharedWith')}</label>
              <div className="px-3 py-2 bg-gray-50 rounded-lg text-gray-700">
                {fileShare.shared_with_username}
              </div>
            </div>
          </div>

          {/* Permissions */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('shares:table.permissions')}</label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_read}
                  onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm">{t('shares:permissions.canRead')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_write}
                  onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm">{t('shares:permissions.canWrite')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_delete}
                  onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm">{t('shares:permissions.canDelete')}</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.can_share}
                  onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm">{t('shares:permissions.canShare')}</span>
              </label>
            </div>
          </div>

          {/* Expiration Date */}
          <div>
            <label className="block text-sm font-medium mb-1">
              {t('shares:form.expirationDate')} ({t('shares:form.expirationHint')})
            </label>
            <input
              type="date"
              value={formData.expires_at || ''}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value || null })}
              min={new Date().toISOString().split('T')[0]}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end space-x-2 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
            >
              {t('shares:buttons.cancel')}
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? t('shares:buttons.saving') : t('shares:buttons.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
