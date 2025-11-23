import { useState } from 'react';
import { X } from 'lucide-react';
import { updateShareLink, type ShareLink, type UpdateShareLinkRequest } from '../api/shares';

interface EditShareLinkModalProps {
  shareLink: ShareLink;
  onClose: () => void;
  onSuccess: () => void;
}

export default function EditShareLinkModal({ shareLink, onClose, onSuccess }: EditShareLinkModalProps) {
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
    } catch (error: any) {
      console.error('Failed to update share link:', error);
      alert(error.response?.data?.detail || 'Failed to update share link');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Edit Share Link</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Info (read-only) */}
          <div>
            <label className="block text-sm font-medium mb-1">File</label>
            <div className="px-3 py-2 bg-gray-50 rounded-lg text-gray-700">
              {shareLink.file_name}
            </div>
          </div>

          {/* Password */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium">Password Protection</label>
              <label className="flex items-center text-sm">
                <input
                  type="checkbox"
                  checked={changePassword}
                  onChange={(e) => setChangePassword(e.target.checked)}
                  className="mr-2"
                />
                Change Password
              </label>
            </div>
            {shareLink.has_password && !changePassword && (
              <div className="text-sm text-gray-600 px-3 py-2 bg-blue-50 rounded-lg">
                🔒 Currently password protected
              </div>
            )}
            {changePassword && (
              <>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Leave empty to remove password"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Leave empty to remove password protection
                </p>
              </>
            )}
          </div>

          {/* Permissions */}
          <div className="grid grid-cols-2 gap-4">
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={formData.allow_download}
                onChange={(e) => setFormData({ ...formData, allow_download: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm">Allow Download</span>
            </label>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={formData.allow_preview}
                onChange={(e) => setFormData({ ...formData, allow_preview: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm">Allow Preview</span>
            </label>
          </div>

          {/* Max Downloads */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Max Downloads (leave empty for unlimited)
            </label>
            <input
              type="number"
              min="1"
              value={formData.max_downloads || ''}
              onChange={(e) => setFormData({ ...formData, max_downloads: e.target.value ? Number(e.target.value) : null })}
              placeholder="Unlimited"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Current downloads: {shareLink.download_count}
            </p>
          </div>

          {/* Expiration Date */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Expiration Date (leave empty for no expiration)
            </label>
            <input
              type="date"
              value={formData.expires_at || ''}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value || null })}
              min={new Date().toISOString().split('T')[0]}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium mb-1">Description (optional)</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Add a description..."
              rows={3}
              maxLength={500}
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
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
