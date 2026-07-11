import { useTranslation } from 'react-i18next';
import { ByteSizeInput } from '../../ui/ByteSizeInput';
import type { UserVCLStats, VCLSettingsUpdate } from '../../../types/vcl';

export function VclEditUserModal({
  editingUser,
  editForm,
  actionLoading,
  onMaxSizeChange,
  onEnabledChange,
  onCancel,
  onSave,
}: {
  editingUser: UserVCLStats;
  editForm: VCLSettingsUpdate;
  actionLoading: boolean;
  onMaxSizeChange: (bytes: number) => void;
  onEnabledChange: (v: boolean) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const { t } = useTranslation('admin');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-slate-900 rounded-xl shadow-2xl border border-slate-800 w-full max-w-md">
        <div className="p-6 border-b border-slate-800">
          <h3 className="text-lg font-semibold text-white">
            {t('vcl.editModal.title', { username: editingUser.username })}
          </h3>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              {t('vcl.editModal.maxSizeLabel')}
            </label>
            <ByteSizeInput
              value={editForm.max_size_bytes || 0}
              onChange={(bytes) => onMaxSizeChange(bytes)}
            />
          </div>
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={editForm.is_enabled ?? true}
                onChange={(e) => onEnabledChange(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-slate-800"
              />
              <span className="text-sm text-slate-300">{t('vcl.editModal.enableVcl')}</span>
            </label>
          </div>
        </div>
        <div className="p-6 border-t border-slate-800 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={onSave}
            disabled={actionLoading}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
