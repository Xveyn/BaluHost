import { useTranslation } from 'react-i18next';
import { Trash2, Edit, CheckCircle, XCircle } from 'lucide-react';
import type { UserPublic } from '../../api/users';

interface UserCardListProps {
  users: UserPublic[];
  selectedUsers: Set<number>;
  onToggleSelection: (id: number) => void;
  onEdit: (user: UserPublic) => void;
  onDelete: (userId: number) => void;
  onToggleActive: (userId: number) => void;
}

export function UserCardList({
  users,
  selectedUsers,
  onToggleSelection,
  onEdit,
  onDelete,
  onToggleActive,
}: UserCardListProps) {
  const { t } = useTranslation('admin');

  if (users.length === 0) {
    return (
      <div className="lg:hidden card border-slate-800/60 bg-slate-900/55 py-12 text-center">
        <p className="text-sm text-slate-500">{t('users.noUsersFound')}</p>
      </div>
    );
  }

  return (
    <div className="lg:hidden space-y-3">
      {users.map((user) => (
        <div key={user.id} className="card border-slate-800/60 bg-slate-900/55 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <input
                type="checkbox"
                checked={selectedUsers.has(user.id)}
                onChange={() => onToggleSelection(user.id)}
                className="h-5 w-5 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500 flex-shrink-0"
              />
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/70 text-base font-semibold text-slate-300 flex-shrink-0">
                {(user.username ?? '?').charAt(0).toUpperCase()}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-white truncate">{user.username}</p>
                <p className="text-xs text-slate-400 truncate">{user.email || 'No email'}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => onEdit(user)}
                className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2.5 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
                title={t('users.editUser')}
              >
                <Edit className="h-4 w-4" />
              </button>
              <button
                onClick={() => onDelete(user.id)}
                className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2.5 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20 touch-manipulation active:scale-95"
                title={t('users.deleteUser')}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                user.role === 'admin'
                  ? 'border border-sky-500/40 bg-sky-500/15 text-sky-200'
                  : 'border border-slate-700/70 bg-slate-900/70 text-slate-300'
              }`}
            >
              {user.role}
            </span>
            <button
              onClick={() => onToggleActive(user.id)}
              className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition touch-manipulation active:scale-95 ${
                user.is_active
                  ? 'border border-green-500/40 bg-green-500/15 text-green-200'
                  : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
              }`}
            >
              {user.is_active ? (
                <>
                  <CheckCircle className="h-3 w-3" />
                  {t('users.status.active')}
                </>
              ) : (
                <>
                  <XCircle className="h-3 w-3" />
                  {t('users.status.inactive')}
                </>
              )}
            </button>
            <span className="text-xs text-slate-500">
              {t('users.fields.created')} {new Date(user.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
