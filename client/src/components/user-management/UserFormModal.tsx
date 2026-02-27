import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { UserPublic } from '../../api/users';
import type { UserFormData } from '../../hooks/useUserManagement';

interface UserFormModalProps {
  open: boolean;
  editingUser: UserPublic | null;
  onClose: () => void;
  onSubmit: (form: UserFormData, editingUser: UserPublic | null) => Promise<boolean>;
}

const emptyForm: UserFormData = {
  username: '',
  email: '',
  password: '',
  role: 'user',
  is_active: true,
};

export function UserFormModal({ open, editingUser, onClose, onSubmit }: UserFormModalProps) {
  const { t } = useTranslation('admin');
  const [formData, setFormData] = useState<UserFormData>(emptyForm);

  useEffect(() => {
    if (editingUser) {
      setFormData({
        username: editingUser.username,
        email: editingUser.email ?? '',
        password: '',
        role: editingUser.role,
        is_active: editingUser.is_active,
      });
    } else {
      setFormData(emptyForm);
    }
  }, [editingUser, open]);

  if (!open) return null;

  const handleSubmit = async () => {
    const success = await onSubmit(formData, editingUser);
    if (success) onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-4 sm:p-6 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="mb-3 sm:mb-4 flex items-center justify-between">
          <h2 className="text-lg sm:text-xl font-semibold text-white">
            {editingUser ? t('users.editUser') : t('users.createUser')}
          </h2>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-slate-800 touch-manipulation active:scale-95">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        <div className="space-y-3 sm:space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {t('users.fields.username')}
            </label>
            <input
              type="text"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder={t('users.placeholders.enterUsername')}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {t('users.fields.emailOptional')}
            </label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder={t('users.placeholders.enterEmail')}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {editingUser ? t('users.fields.passwordKeep') : t('users.fields.password')}
            </label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder={t('users.placeholders.enterPassword')}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              {t('users.fields.role')}
            </label>
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="user">{t('users.roles.user')}</option>
              <option value="admin">{t('users.roles.admin')}</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_active"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
            />
            <label htmlFor="is_active" className="text-sm text-slate-300">
              {t('users.fields.activeUser')}
            </label>
          </div>
        </div>

        <div className="mt-4 sm:mt-6 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
          >
            {t('users.buttons.cancel')}
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
          >
            {editingUser ? t('users.buttons.update') : t('users.buttons.create')}
          </button>
        </div>
      </div>
    </div>
  );
}
