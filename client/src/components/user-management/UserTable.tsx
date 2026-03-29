import { useTranslation } from 'react-i18next';
import { Trash2, Edit, CheckCircle, XCircle } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import type { SortDirection } from '../../hooks/useSortableTable';
import type { UserPublic } from '../../api/users';

interface UserTableProps {
  users: UserPublic[];
  selectedUsers: Set<number>;
  sortBy: string | null;
  sortOrder: SortDirection;
  onSort: (field: string) => void;
  onToggleSelection: (id: number) => void;
  onToggleAll: () => void;
  onEdit: (user: UserPublic) => void;
  onDelete: (userId: number) => void;
  onToggleActive: (userId: number) => void;
}

export function UserTable({
  users,
  selectedUsers,
  sortBy,
  sortOrder,
  onSort,
  onToggleSelection,
  onToggleAll,
  onEdit,
  onDelete,
  onToggleActive,
}: UserTableProps) {
  const { t } = useTranslation(['admin', 'common']);

  return (
    <div className="hidden lg:block card border-slate-800/60 bg-slate-900/55">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-800/60">
          <thead>
            <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
              <th className="px-6 py-4">
                <input
                  type="checkbox"
                  checked={selectedUsers.size === users.length && users.length > 0}
                  onChange={onToggleAll}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                />
              </th>
              <SortableHeader label={t('users.fields.username')} sortKey="username" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.email')} sortKey="email" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.role')} sortKey="role" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.status')} sortKey="is_active" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <SortableHeader label={t('users.fields.created')} sortKey="created_at" activeSortKey={sortBy} sortDirection={sortOrder} onSort={onSort} className="px-6 py-4" />
              <th className="px-6 py-4">{t('users.fields.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {users.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  {t('users.noUsersFound')}
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id} className="group transition hover:bg-slate-900/70">
                  <td className="px-6 py-4">
                    <input
                      type="checkbox"
                      checked={selectedUsers.has(user.id)}
                      onChange={() => onToggleSelection(user.id)}
                      className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-200">
                    <div className="flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/70 text-sm font-semibold text-slate-300">
                        {(user.username ?? '?').charAt(0).toUpperCase()}
                      </span>
                      <span className="font-medium group-hover:text-white">{user.username}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-400">{user.email}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        user.role === 'admin'
                          ? 'border border-sky-500/40 bg-sky-500/15 text-sky-200'
                          : 'border border-slate-700/70 bg-slate-900/70 text-slate-300'
                      }`}
                    >
                      {user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => onToggleActive(user.id)}
                      className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition ${
                        user.is_active
                          ? 'border border-green-500/40 bg-green-500/15 text-green-200 hover:bg-green-500/25'
                          : 'border border-slate-700/70 bg-slate-900/70 text-slate-400 hover:bg-slate-800/70'
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
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-400">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onEdit(user)}
                        className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                        title={t('users.editUser')}
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => onDelete(user.id)}
                        className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                        title={t('users.deleteUser')}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
